"""Named committee responsibilities; explicit additive grants, never superuser."""
BASE=['dic.can_view_dic_operations']
ROLES={
 'DIC Operations Administrators':BASE+['dic.view_registrationorder','dic.view_participant','dic.view_houseallocation','dic.can_view_dic_audit','dic.can_export_dic_reports'],
 'DIC Registration Managers':BASE+['dic.view_registrationorder','dic.view_participant','dic.change_registrationorder','dic.delete_registrationorder','dic.can_manage_registration_access','dic.view_houseallocation'],
 'DIC Check-in Officers':BASE+['dic.view_participant','dic.can_check_in_dic_participants','dic.can_view_dic_ids'],
 'DIC ID Officers':BASE+['dic.view_participant','dic.can_view_dic_ids','dic.can_manage_dic_ids'],
 'DIC Housing Officers':BASE+['dic.view_house','dic.view_houseallocation','dic.view_participant','dic.can_allocate_participants'],
 'DIC Scoring Officers':BASE+['dic.can_view_dic_scores','dic.can_record_dic_scores'],
 'DIC Finance Officers':BASE+['dic.can_view_dic_finance','dic.view_registrationorder','dic_finance.can_view_details_finance','dic_finance.can_record_income_finance','dic_finance.can_submit_expense_finance'],
 'DIC Report Officers':BASE+['dic.can_export_dic_reports','dic.view_registrationorder','dic.view_participant'],
 'DIC Media Editors':BASE+['dic.view_campphotograph','dic.add_campphotograph','dic.change_campphotograph','dic.delete_campphotograph','dic.view_campvideo','dic.add_campvideo','dic.change_campvideo','dic.delete_campvideo','dic.view_lecturerecording','dic.add_lecturerecording','dic.change_lecturerecording','dic.delete_lecturerecording','dic.view_timetableentry'],
 'DIC Media Publishers':BASE+['dic.view_campphotograph','dic.change_campphotograph','dic.publish_campphotograph','dic.view_campvideo','dic.change_campvideo','dic.publish_campvideo','dic.view_lecturerecording','dic.change_lecturerecording','dic.publish_lecturerecording'],
 # A single media professional manages routine editing AND publishing directly.
 # Assignments remain owner-controlled; no grants to any existing account.
 'DAWANA Media Studio Personnel':[
     'dic.view_campphotograph','dic.add_campphotograph','dic.change_campphotograph','dic.publish_campphotograph',
     'dic.view_campvideo','dic.add_campvideo','dic.change_campvideo','dic.publish_campvideo',
     'dic.view_lecturerecording','dic.add_lecturerecording','dic.change_lecturerecording','dic.publish_lecturerecording',
     'dic.view_campflyer','dic.add_campflyer','dic.change_campflyer','dic.delete_campflyer','dic.publish_campflyer',
     'dic.view_promovideo','dic.add_promovideo','dic.change_promovideo','dic.delete_promovideo','dic.publish_promovideo',
     'dic.view_lecturer','dic.add_lecturer','dic.change_lecturer',
     'dic.view_lecturerappearance','dic.add_lecturerappearance','dic.change_lecturerappearance',
     'dic.view_campactivity','dic.add_campactivity','dic.change_campactivity','dic.delete_campactivity','dic.publish_campactivity',
     'dic.view_studiohostedvideo','dic.add_studiohostedvideo','dic.change_studiohostedvideo','dic.delete_studiohostedvideo',
     'dic.publish_studiohostedvideo',
     'dic.view_timetableentry',
     'dic.view_studioasset','dic.add_studioasset','dic.change_studioasset',
     'dic.view_studioplacement','dic.add_studioplacement','dic.change_studioplacement',
     'dic.manage_studio_assets','dic.publish_studio_placements',
 ],
 'DIC Programme Editors':BASE+['dic.view_timetableentry','dic.manage_dic_timetables'],
 'DIC Programme Publishers':BASE+['dic.view_timetableentry','dic.publish_dic_timetables'],
 'DIC Certificate Officers':BASE+['dic.view_participationcertificate','dic.manage_dic_certificates','dic.release_dic_certificates'],
}
