"""Explicit single-source requirements for synthetic report fixtures, not legal manifests."""


def declared_requirements(key):
    return {
        "requirements": [
            {
                "key": key,
                "title": "SYNTHETIC retained source presentation",
                "disposition": "REQUIRED",
                "source_required": True,
                "basis": "Synthetic source presentation requirement; not a complete statutory manifest",
            }
        ],
        "requirements_assessed": True,
        "requirements_basis": "Synthetic declared fixture scope independently reviewed; no statutory completeness qualification",
    }
