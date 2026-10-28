"""Final database-free release suite and source migration manifest.

Actual applied/pending database state is intentionally UNVERIFIED here.
"""
import json
from pathlib import Path
import uuid
from validate_dic_phase5_policy import main as run_policy
from validate_dic_phase6_policy import check_graph


def release_graph(loader,actual):
    check_graph(loader,actual)
    from config.release_migrations import plan_manifest
    target=loader.graph.leaf_nodes()
    ordered=[];seen=set()
    for leaf in sorted(target):
        for node in loader.graph.forwards_plan(leaf):
            if node not in seen:seen.add(node);ordered.append(node)
    manifest=plan_manifest(loader,[(loader.get_migration(*node),False) for node in ordered],
        'UNVERIFIED','source_graph_only')
    manifest['applied_database_state']='UNVERIFIED'
    manifest['warning']='Entire source graph, not an approved pending database migration plan.'
    output=Path(__file__).resolve().parents[1]/'output'/'acceptance'
    output.mkdir(parents=True,exist_ok=True)
    path=output/('release-source-graph-'+uuid.uuid4().hex+'.json')
    path.write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print('Source graph receipt: '+str(path))


if __name__=='__main__':
    run_policy(extra_tests=[
        'dic.test_release_readiness.ReleaseReadinessTests','dic.test_reporting.ReportingPolicyTests',
        'dic_finance.tests.FinancePolicyTests','dic_movement.tests.MovementPolicyTests',
        'dic.test_checkin.CampCheckInTests','dic.test_house_configuration.FinalHouseConfigurationTests',
        'dic.tests.PaystackClientTests','dic.test_registration_privacy.RegistrationPrivacyPolicyTests',
        'dic.test_tutor_registration.TutorPolicyTests'],phase_label='Final release',graph_check=release_graph)
