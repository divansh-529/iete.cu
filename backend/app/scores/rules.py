"""Who scores whom, and out of how much (decided by the Chairperson, 2026-11-01).
Every card adds up to 20. The Chairperson is not scored."""
from decimal import Decimal

D = Decimal
RULES: dict[str, dict[str, Decimal]] = {
    "member":          {"lead": D(5), "secretary": D(5), "vice_chair": D(5), "chairperson": D(5)},
    "lead":            {"joint_secretary": D(5), "secretary": D(5), "vice_chair": D(5), "chairperson": D(5)},
    "joint_secretary": {"secretary": D(7), "vice_chair": D(7), "chairperson": D(6)},
    "vice_chair":      {"secretary": D(10), "chairperson": D(10)},
    "secretary":       {"vice_chair": D(10), "chairperson": D(10)},
}
ROUND_MAX = D(20)
assert all(sum(slots.values()) == ROUND_MAX for slots in RULES.values())

CATEGORY_LABELS = {"member": "Member", "lead": "Department Lead", "joint_secretary": "Joint Secretary",
                   "secretary": "Secretary", "vice_chair": "Vice Chairperson"}
SLOT_LABELS = {"lead": "Department Lead", "joint_secretary": "Joint Secretary", "secretary": "Secretary",
               "vice_chair": "Vice Chairperson", "chairperson": "Chairperson"}

# Leadership positions are recognised by title (they are organisation-wide, department_id is null).
LEADERSHIP_TITLES = {"chairperson": "chairperson", "vice chairperson": "vice_chair",
                     "secretary": "secretary", "joint secretary": "joint_secretary"}
