"""Phase 6 database-free reporting/Finance/privacy checks. No schema application."""
import importlib.util
from pathlib import Path


def check_graph(loader,actual):
    for target,names in [
        (('dic_finance','0001_initial'),('category','entry','budgetrevision','reconciliation')),
        (('dic_movement','0001_initial'),('movement',))]:
        plan=loader.graph.forwards_plan(target)
        if ('dic','0027_feedback_welfare') in plan or ('dic','0026_house_score_transaction') not in plan:
            raise RuntimeError('Unexpected Finance/Movement migration dependencies.')
        prepared=loader.project_state(target)
        for name in names:
            if actual.models[target[0],name]!=prepared.models[target[0],name]:
                raise RuntimeError('Reporting source model/migration mismatch: '+name)


def main():
    path=Path(__file__).with_name('validate_dic_phase5_policy.py')
    spec=importlib.util.spec_from_file_location('phase6_shared_policy',path)
    policy=importlib.util.module_from_spec(spec);spec.loader.exec_module(policy)
    policy.main(extra_tests=[
        'dic.test_reporting.ReportingPolicyTests','dic_finance.tests.FinancePolicyTests',
        'dic_movement.tests.MovementPolicyTests','dic.test_checkin.CampCheckInTests',
        'dic.test_house_configuration.FinalHouseConfigurationTests'],
        phase_label='Phase 6',graph_check=check_graph)


if __name__=='__main__':
    main()
