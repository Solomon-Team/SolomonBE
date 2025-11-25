# app/services/seed_magic_auth.py
from sqlalchemy.orm import Session
from app.models.structure import Structure
from app.models.user import User
from app.models.role import Role
from app.models.structure_join_code import StructureJoinCode
from app.core.security import hash_password, generate_join_code
from datetime import datetime, timedelta, timezone


# Default role permissions for each role type
DEFAULT_PERMISSIONS = {
    "OWNER": {
        "users.admin": True,
        "structures.manage": True,
        "codes.create": True,
        "members.kick": True,
        "locations.manage": True,
        "items.manage": True,
        "trades.view_all": True,
        "inventory.admin": True,
    },
    "ADMIN": {
        "structures.manage": True,
        "codes.create": True,
        "members.kick": True,
        "locations.manage": True,
        "items.manage": True,
        "trades.view_all": True,
        "inventory.admin": True,
    },
    "MEMBER": {
        "inventory.view": True,
        "trades.create": True,
    }
}


def seed_magic_auth_system(db: Session):
    """
    Seed the database with initial data for the magic auth system.
    Creates demo structures, roles, users, and join codes.
    """
    print("[SEED] Seeding magic auth system...")

    # 1. Create Structures
    structures_data = [
        {
            "id": "GPR",
            "name": "Golden Prosperity Republic",
            "display_name": "Golden Prosperity",
            "description": "The original demo structure for testing and development",
            "is_active": True
        },
        {
            "id": "WHB",
            "name": "Warehouse Base",
            "display_name": "Warehouse Base",
            "description": "Secondary test structure for multi-tenant testing",
            "is_active": True
        }
    ]

    for struct_data in structures_data:
        existing = db.query(Structure).filter(Structure.id == struct_data["id"]).first()
        if not existing:
            structure = Structure(**struct_data)
            db.add(structure)
            print(f"  [OK] Created structure: {struct_data['display_name']}")

    db.commit()

    # 2. Create Roles for each structure
    for struct_id in ["GPR", "WHB"]:
        for role_type in ["OWNER", "ADMIN", "MEMBER"]:
            existing = db.query(Role).filter(
                Role.structure_id == struct_id,
                Role.role_type == role_type
            ).first()

            if not existing:
                role = Role(
                    structure_id=struct_id,
                    role_type=role_type,
                    name=role_type.capitalize(),
                    permissions=DEFAULT_PERMISSIONS[role_type],
                    is_custom=False
                )
                db.add(role)
                print(f"  [OK] Created role: {struct_id}/{role_type}")

    db.commit()

    # 3. Create Demo Users
    demo_users = [
        {
            "mc_uuid": "550e8400-e29b-41d4-a716-446655440000",
            "username": "DemoOwner",
            "password": "Password123!",
            "structure_id": "GPR",
            "membership_status": "member",
            "roles": ["OWNER"]
        },
        {
            "mc_uuid": "550e8400-e29b-41d4-a716-446655440001",
            "username": "DemoAdmin",
            "password": "Password123!",
            "structure_id": "GPR",
            "membership_status": "member",
            "roles": ["ADMIN"]
        },
        {
            "mc_uuid": "550e8400-e29b-41d4-a716-446655440002",
            "username": "DemoMember",
            "password": "Password123!",
            "structure_id": "GPR",
            "membership_status": "member",
            "roles": ["MEMBER"]
        },
        {
            "mc_uuid": "550e8400-e29b-41d4-a716-446655440003",
            "username": "NewPlayer",
            "password": None,
            "structure_id": None,  # Not in any structure yet
            "membership_status": "unassigned",
            "roles": []
        },
        {
            "mc_uuid": "550e8400-e29b-41d4-a716-446655440004",
            "username": "GuestPlayer",
            "password": None,
            "structure_id": "GPR",  # Requested to join GPR
            "membership_status": "guest",  # Waiting for approval
            "roles": []
        }
    ]

    for user_data in demo_users:
        existing = db.query(User).filter(User.mc_uuid == user_data["mc_uuid"]).first()

        if not existing:
            user = User(
                mc_uuid=user_data["mc_uuid"],
                username=user_data["username"],
                hashed_password=hash_password(user_data["password"]) if user_data["password"] else None,
                has_password=user_data["password"] is not None,
                structure_id=user_data["structure_id"],
                membership_status=user_data["membership_status"]
            )
            db.add(user)
            db.flush()

            # Assign roles
            if user_data["roles"] and user_data["structure_id"]:
                for role_type in user_data["roles"]:
                    role = db.query(Role).filter(
                        Role.structure_id == user_data["structure_id"],
                        Role.role_type == role_type
                    ).first()
                    if role:
                        user.roles.append(role)

            print(f"  [OK] Created user: {user_data['username']} (structure: {user_data['structure_id'] or 'None'})")

    db.commit()

    # 4. Create Demo Join Codes
    join_codes_data = [
        {
            "structure_id": "GPR",
            "expires_at": datetime.now(timezone.utc) + timedelta(days=30),
            "max_uses": 100
        },
        {
            "structure_id": "WHB",
            "expires_at": None,  # Never expires
            "max_uses": None  # Unlimited uses
        }
    ]

    for code_data in join_codes_data:
        # Get owner user for this structure
        owner_user = db.query(User).filter(
            User.structure_id == code_data["structure_id"]
        ).join(User.roles).filter(
            Role.role_type == "OWNER"
        ).first()

        if owner_user:
            code_str = generate_join_code(code_data["structure_id"])

            # Check if similar code already exists
            existing = db.query(StructureJoinCode).filter(
                StructureJoinCode.structure_id == code_data["structure_id"],
                StructureJoinCode.is_active == True
            ).first()

            if not existing:
                join_code = StructureJoinCode(
                    code=code_str,
                    structure_id=code_data["structure_id"],
                    created_by_user_id=owner_user.id,
                    expires_at=code_data["expires_at"],
                    max_uses=code_data["max_uses"],
                    used_count=0,
                    is_active=True
                )
                db.add(join_code)
                print(f"  [OK] Created join code for {code_data['structure_id']}: {code_str}")

    db.commit()

    print("[SEED] Magic auth system seed completed!")
    print("\n[INFO] Demo Accounts:")
    print("   Owner:      username=DemoOwner,    password=Password123! (member of GPR)")
    print("   Admin:      username=DemoAdmin,    password=Password123! (member of GPR)")
    print("   Member:     username=DemoMember,   password=Password123! (member of GPR)")
    print("   Unassigned: username=NewPlayer     (no password, no structure)")
    print("   Guest:      username=GuestPlayer   (no password, guest of GPR - pending approval)\n")
