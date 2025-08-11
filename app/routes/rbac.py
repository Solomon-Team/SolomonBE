# app/routes/rbac.py
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import select

from app.services.deps import get_db, get_current_structure, require_perm
from app.models.user import User
from app.models.role import Role
from app.models.location import Location
from app.models.location_guild_master import LocationGuildMaster

router = APIRouter(prefix="/rbac", tags=["RBAC"])
view_guard = require_perm("rbac.view")

@router.get("/graph")
def get_rbac_graph(
    include_roles: bool = True,
    include_users: bool = True,
    include_locations: bool = True,
    db: Session = Depends(get_db),
    structure_id: str = Depends(get_current_structure),
    _: User = Depends(view_guard),
):
    nodes: list[dict] = []
    edges: list[dict] = []

    # Keep track to avoid duplicates
    seen_node_ids: set[str] = set()

    def add_node(kind: str, raw_id: int, label: str):
        nid = f"{'role' if kind=='role' else 'user' if kind=='user' else 'loc'}:{raw_id}"
        if nid in seen_node_ids:
            return
        nodes.append({"data": {"id": nid, "label": label, "category": ("role" if kind=="role" else "user" if kind=="user" else "location")}})
        seen_node_ids.add(nid)

    def add_edge(source: str, target: str, etype: str):
        edges.append({"data": {"source": source, "target": target, "type": etype}})

    # Roles
    roles_by_id: dict[int, Role] = {}
    if include_roles:
        roles = db.execute(
            select(Role).where(Role.structure_id == structure_id).order_by(Role.name.asc())
        ).scalars().all()
        for r in roles:
            roles_by_id[r.id] = r
            add_node("role", r.id, r.name)

    # Users (+ roles eager-loaded)
    users: list[User] = []
    if include_users:
        users = (
            db.query(User)
              .options(joinedload(User.roles))
              .filter(User.structure_id == structure_id)
              .order_by(User.username.asc())
              .all()
        )
        for u in users:
            add_node("user", u.id, u.username)
            # role -> user edges (multi-role)
            for r in u.roles:
                # if roles are not requested we still may need their nodes as edge sources
                if include_roles:
                    pass
                else:
                    add_node("role", r.id, r.name)
                add_edge(f"role:{r.id}", f"user:{u.id}", "assigned")

    # Locations + guildmaster assignments (user -> location)
    if include_locations:
        locs = db.query(Location).filter(Location.structure_id == structure_id).order_by(Location.name.asc()).all()
        for loc in locs:
            add_node("loc", loc.id, loc.name)

        # link guild masters to their locations
        gm_links = (
            db.query(LocationGuildMaster)
              .join(Location, Location.id == LocationGuildMaster.location_id)
              .filter(Location.structure_id == structure_id)
              .all()
        )
        for gm in gm_links:
            # ensure user node exists even if users list was skipped
            if include_users is False:
                add_node("user", gm.user_id, f"user:{gm.user_id}")
            add_edge(f"user:{gm.user_id}", f"loc:{gm.location_id}", "manages")

    return {"nodes": nodes, "edges": edges}
