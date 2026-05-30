from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

SUPPORTED_VTK_EXTENSIONS = {".vtp", ".vtu"}
SUPPORTED_AR_EXTENSIONS = {".glb", ".usdz"}
MODEL_METADATA_FILE = "model.yaml"


class MetadataError(ValueError):
    """Raised when a model metadata file cannot be used."""


@dataclass(frozen=True)
class DefaultScalar:
    name: str | None = None
    mode: str = "scalar"


@dataclass(frozen=True)
class ArAssets:
    glb: Path | None = None
    usdz: Path | None = None

    @property
    def has_assets(self) -> bool:
        return self.glb is not None or self.usdz is not None


@dataclass(frozen=True)
class PartFile:
    path: Path
    label: str


@dataclass(frozen=True)
class ModelPart:
    id: str
    label: str
    files: tuple[PartFile, ...]
    color: str | None = None

    def file_for_timestep(self, timestep_index: int) -> PartFile:
        if len(self.files) == 1:
            return self.files[0]
        return self.files[timestep_index]


@dataclass(frozen=True)
class GlyphPreset:
    id: str
    label: str
    part_id: str
    vectors: str
    scale_factor: float = 1.0
    density: float = 1.0
    color: str | None = None
    color_by: DefaultScalar = DefaultScalar()


@dataclass(frozen=True)
class ModelMetadata:
    id: str
    title: str
    root: Path
    library_root: Path
    parts: tuple[ModelPart, ...]
    description: str = ""
    default_scalar: DefaultScalar = DefaultScalar()
    ar_assets: ArAssets = ArAssets()
    glyphs: tuple[GlyphPreset, ...] = ()

    @property
    def is_time_series(self) -> bool:
        return any(len(part.files) > 1 for part in self.parts)

    @property
    def timestep_count(self) -> int:
        return max(len(part.files) for part in self.parts)

    @property
    def timestep_labels(self) -> list[str]:
        longest = max(self.parts, key=lambda part: len(part.files))
        return [part_file.label for part_file in longest.files]

    def asset_url(self, path: Path | None, endpoint: str = "/model-assets") -> str:
        if path is None:
            return ""
        relative = path.relative_to(self.library_root)
        return f"{endpoint.rstrip('/')}/{relative.as_posix()}"

    def part_by_id(self, part_id: str) -> ModelPart:
        for part in self.parts:
            if part.id == part_id:
                return part
        raise KeyError(part_id)

    def summary(self) -> dict[str, object]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "kind": "time series" if self.is_time_series else "static",
            "part_count": len(self.parts),
            "timestep_count": self.timestep_count,
            "has_ar": self.ar_assets.has_assets,
            "analysis_count": len(self.glyphs),
            "glb_url": self.asset_url(self.ar_assets.glb),
            "usdz_url": self.asset_url(self.ar_assets.usdz),
        }


def discover_models(library_root: str | Path) -> list[ModelMetadata]:
    library = Path(library_root).expanduser().resolve()
    if not library.exists():
        return []

    metadata_paths: list[Path] = []
    if (library / MODEL_METADATA_FILE).exists():
        metadata_paths.append(library / MODEL_METADATA_FILE)

    for child in sorted(path for path in library.iterdir() if path.is_dir()):
        metadata_path = child / MODEL_METADATA_FILE
        if metadata_path.exists():
            metadata_paths.append(metadata_path)

    return [load_model_metadata(path, library_root=library) for path in metadata_paths]


def load_model_metadata(path: str | Path, library_root: str | Path | None = None) -> ModelMetadata:
    metadata_path = Path(path).expanduser().resolve()
    root = metadata_path.parent
    library = Path(library_root).expanduser().resolve() if library_root else root
    payload = _read_yaml_mapping(metadata_path)

    model_id = _required_slug(payload, "id", metadata_path)
    title = _required_text(payload, "title", metadata_path)
    description = str(payload.get("description", "") or "")
    default_scalar = _parse_default_scalar(payload.get("default_scalar"))
    ar_assets = _parse_ar_assets(root, payload.get("ar"))
    parts = _parse_parts(root, payload.get("parts"), metadata_path)
    _validate_timestep_lengths(parts, metadata_path)
    glyphs = _parse_visualizations(
        payload.get("visualizations"),
        metadata_path=metadata_path,
        parts=parts,
    )

    return ModelMetadata(
        id=model_id,
        title=title,
        description=description,
        root=root,
        library_root=library,
        default_scalar=default_scalar,
        ar_assets=ar_assets,
        glyphs=tuple(glyphs),
        parts=tuple(parts),
    )


def _read_yaml_mapping(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise MetadataError(f"Metadata file does not exist: {path}")
    try:
        payload = yaml.safe_load(path.read_text())
    except yaml.YAMLError as exc:
        raise MetadataError(f"Invalid YAML in {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise MetadataError(f"{path} must contain a top-level mapping.")
    return payload


def _required_text(payload: dict[str, Any], key: str, metadata_path: Path) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise MetadataError(f"{metadata_path} requires a non-empty '{key}' field.")
    return value.strip()


def _required_slug(payload: dict[str, Any], key: str, metadata_path: Path) -> str:
    value = _required_text(payload, key, metadata_path)
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", value):
        raise MetadataError(f"{metadata_path} field '{key}' must be a lowercase slug.")
    return value


def _parse_default_scalar(value: Any) -> DefaultScalar:
    if value is None:
        return DefaultScalar()
    if not isinstance(value, dict):
        raise MetadataError("'default_scalar' must be a mapping when provided.")
    name = value.get("name")
    mode = value.get("mode", "scalar")
    if name is not None and not isinstance(name, str):
        raise MetadataError("'default_scalar.name' must be a string.")
    if mode not in {"scalar", "magnitude"}:
        raise MetadataError("'default_scalar.mode' must be 'scalar' or 'magnitude'.")
    return DefaultScalar(name=name, mode=mode)


def _parse_ar_assets(root: Path, value: Any) -> ArAssets:
    if value is None:
        return ArAssets()
    if not isinstance(value, dict):
        raise MetadataError("'ar' must be a mapping when provided.")

    glb = _optional_existing_asset(root, value.get("glb"), ".glb")
    usdz = _optional_existing_asset(root, value.get("usdz"), ".usdz")
    return ArAssets(glb=glb, usdz=usdz)


def _optional_existing_asset(root: Path, value: Any, extension: str) -> Path | None:
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise MetadataError(f"AR asset path for {extension} must be a string.")
    path = (root / value).resolve()
    if path.suffix.lower() != extension:
        raise MetadataError(f"AR asset {path} must use the {extension} extension.")
    if not path.exists():
        raise MetadataError(f"AR asset does not exist: {path}")
    return path


def _parse_parts(root: Path, value: Any, metadata_path: Path) -> list[ModelPart]:
    if not isinstance(value, list) or not value:
        raise MetadataError(f"{metadata_path} requires a non-empty 'parts' list.")

    parts: list[ModelPart] = []
    seen_ids: set[str] = set()
    for raw_part in value:
        if not isinstance(raw_part, dict):
            raise MetadataError("Each part must be a mapping.")
        part_id = _required_slug(raw_part, "id", metadata_path)
        if part_id in seen_ids:
            raise MetadataError(f"Duplicate part id: {part_id}")
        seen_ids.add(part_id)
        label = str(raw_part.get("label") or part_id.replace("-", " ").title())
        color = raw_part.get("color")
        if color is not None and not re.fullmatch(r"#[0-9a-fA-F]{6}", str(color)):
            raise MetadataError(f"Part '{part_id}' color must use #RRGGBB format.")
        files = _parse_part_files(root, raw_part.get("files"), part_id)
        parts.append(
            ModelPart(
                id=part_id,
                label=label,
                color=str(color).upper() if color is not None else None,
                files=tuple(files),
            )
        )
    return parts


def _parse_part_files(root: Path, value: Any, part_id: str) -> list[PartFile]:
    if not isinstance(value, list) or not value:
        raise MetadataError(f"Part '{part_id}' requires a non-empty 'files' list.")

    files: list[PartFile] = []
    for index, raw_file in enumerate(value):
        if not isinstance(raw_file, dict):
            raise MetadataError(f"Each file for part '{part_id}' must be a mapping.")
        raw_path = raw_file.get("path")
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise MetadataError(f"Each file for part '{part_id}' requires a path.")
        path = (root / raw_path).resolve()
        if path.suffix.lower() not in SUPPORTED_VTK_EXTENSIONS:
            raise MetadataError(f"Unsupported VTK file for part '{part_id}': {path}")
        if not path.exists():
            raise MetadataError(f"Model file does not exist: {path}")
        label = str(raw_file.get("label") or raw_file.get("time") or index)
        files.append(PartFile(path=path, label=label))
    return files


def _validate_timestep_lengths(parts: list[ModelPart], metadata_path: Path) -> None:
    multi_lengths = {len(part.files) for part in parts if len(part.files) > 1}
    if len(multi_lengths) > 1:
        raise MetadataError(
            f"{metadata_path} has inconsistent time-series lengths across parts: {sorted(multi_lengths)}"
        )


def _parse_visualizations(
    value: Any,
    *,
    metadata_path: Path,
    parts: list[ModelPart],
) -> list[GlyphPreset]:
    if value is None:
        return []
    if not isinstance(value, dict):
        raise MetadataError(f"{metadata_path} field 'visualizations' must be a mapping.")

    part_ids = {part.id for part in parts}
    return _parse_glyphs(value.get("glyphs"), metadata_path, part_ids)


def _parse_glyphs(value: Any, metadata_path: Path, part_ids: set[str]) -> list[GlyphPreset]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise MetadataError(f"{metadata_path} field 'visualizations.glyphs' must be a list.")

    presets: list[GlyphPreset] = []
    seen_ids: set[str] = set()
    for raw_preset in value:
        if not isinstance(raw_preset, dict):
            raise MetadataError("Each glyph preset must be a mapping.")
        preset_id = _required_slug(raw_preset, "id", metadata_path)
        if preset_id in seen_ids:
            raise MetadataError(f"Duplicate glyph preset id: {preset_id}")
        seen_ids.add(preset_id)
        part_id = _required_text(raw_preset, "part", metadata_path)
        if part_id not in part_ids:
            raise MetadataError(f"Glyph preset '{preset_id}' references unknown part '{part_id}'.")
        vectors = _required_text(raw_preset, "vectors", metadata_path)
        scale_factor = _optional_number(raw_preset, "scale_factor", metadata_path, default=1.0)
        density = _optional_number(raw_preset, "density", metadata_path, default=1.0)
        if scale_factor <= 0:
            raise MetadataError(f"Glyph preset '{preset_id}' scale_factor must be positive.")
        if density <= 0:
            raise MetadataError(f"Glyph preset '{preset_id}' density must be positive.")
        color = _optional_color(raw_preset.get("color"), f"Glyph preset '{preset_id}'")
        color_by = _parse_default_scalar(raw_preset.get("color_by"))
        presets.append(
            GlyphPreset(
                id=preset_id,
                label=str(raw_preset.get("label") or preset_id.replace("-", " ").title()),
                part_id=part_id,
                vectors=vectors,
                scale_factor=scale_factor,
                density=density,
                color=color,
                color_by=color_by,
            )
        )
    return presets


def _required_number(payload: dict[str, Any], key: str, metadata_path: Path) -> float:
    value = payload.get(key)
    if not isinstance(value, int | float):
        raise MetadataError(f"{metadata_path} requires numeric field '{key}'.")
    return float(value)


def _optional_number(payload: dict[str, Any], key: str, metadata_path: Path, *, default: float) -> float:
    if key not in payload or payload.get(key) is None:
        return default
    value = payload.get(key)
    if not isinstance(value, int | float):
        raise MetadataError(f"{metadata_path} field '{key}' must be numeric.")
    return float(value)


def _optional_color(value: Any, owner: str) -> str | None:
    if value in (None, ""):
        return None
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", str(value)):
        raise MetadataError(f"{owner} color must use #RRGGBB format.")
    return str(value).upper()
