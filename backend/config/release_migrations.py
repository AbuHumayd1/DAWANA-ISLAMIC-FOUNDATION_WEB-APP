"""Exact migration approval contracts. No database access on import."""
import hashlib
import json
from pathlib import Path


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def plan_manifest(loader, plan, database, settings_module, target_identity=None):
    steps=[]
    for migration,backwards in plan:
        if backwards: raise RuntimeError('Backward migration plans are prohibited.')
        module=__import__(migration.__class__.__module__,fromlist=['__file__'])
        steps.append(dict(app=migration.app_label,name=migration.name,
            source_sha256=hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest(),
            run_before=[list(node) for node in migration.run_before],
            dependencies=[list(node) for node in migration.dependencies]))
    value=dict(database=database,settings_module=settings_module,steps=steps)
    if target_identity is not None:
        value['target_identity'] = target_identity
    return {**value,'plan_sha256':digest(value)}


def validate_target(config, expected, actual):
    """Non-secret endpoint, role and PostgreSQL cluster binding."""
    if (str(config.get('HOST')) != expected['host']
            or str(config.get('PORT') or '5432') != expected['port']
            or str(config.get('USER')) != expected['role']):
        raise RuntimeError('Configured migration endpoint/role mismatch.')
    if (actual['database'] != expected['database'] or actual['role'] != expected['role']
            or str(actual['cluster_id']) != expected['cluster_id']):
        raise RuntimeError('Connected migration cluster/database/role mismatch.')


def validate_approval(manifest,approval):
    if not isinstance(approval,dict):
        raise RuntimeError('Migration approval must be an object.')
    if approval.get('manifest')!=manifest:
        raise RuntimeError('Approved migration plan does not match the actual pending plan.')
    if not all(isinstance(approval.get(key),str) and approval[key].strip() for key in
            ('approved_by','approved_at','backup_reference','restore_procedure','rollback_decision')):
        raise RuntimeError('Migration approval requires named approval, backup and restore/rollback evidence.')
