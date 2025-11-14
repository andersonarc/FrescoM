PLATE_TYPES = {
    '96-well': {
        'rows': 8,
        'cols': 12,
        'well_diameter': 6.5,
        'well_spacing': 9.0,
        'well_depth': 10.5,
        'plate_thickness': 2.0,
        'row_labels': ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H'],
        'steps_per_well': 1800  # 9mm * 200 steps/mm
    },
    '384-well': {
        'rows': 16,
        'cols': 24,
        'well_diameter': 3.3,
        'well_spacing': 4.5,
        'well_depth': 11.5,
        'plate_thickness': 2.0,
        'row_labels': ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 
                       'I', 'J', 'K', 'L', 'M', 'N', 'O', 'P'],
        'steps_per_well': 900,  # 4.5mm * 200 steps/mm
    },
    '24-well': {
        'rows': 4,
        'cols': 6,
        'well_diameter': 15.5,
        'well_spacing': 19.3,
        'well_depth': 17.4,
        'plate_thickness': 2.0,
        'row_labels': ['A', 'B', 'C', 'D'],
        'steps_per_well': 3860,  # 19.3mm * 200 steps/mm
    },
    '48-well': {
        'rows': 6,
        'cols': 8,
        'well_diameter': 11.0,
        'well_spacing': 13.0,
        'well_depth': 17.4,
        'plate_thickness': 2.0,
        'row_labels': ['A', 'B', 'C', 'D', 'E', 'F'],
        'steps_per_well': 2600,  # 13.0mm * 200 steps/mm
    },
}

STEPS_PER_MM = 200.0

def get_plate_config(plate_type: str) -> dict:
    if plate_type not in PLATE_TYPES:
        raise ValueError(f"Unknown plate type {plate_type}")
    base = PLATE_TYPES[plate_type].copy()

    # Derived properties
    scale = base['steps_per_well']
    base['bottom_left'] = (0, 0)
    base['top_right'] = ((base['cols'] - 1) * scale, (base['rows'] - 1) * scale)
    return base

def get_available_plate_types() -> list:
    return list(PLATE_TYPES.keys())
