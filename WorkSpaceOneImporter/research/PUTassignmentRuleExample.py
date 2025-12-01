api_doc_example_assignment_rules = {
    """Example from Workspace ONE UEM API Explorer - MAM (Mobile Application Management) REST API V2
 at  https://as135.awmdm.com/API/help/#!/apis/10001?!%2FAppsV2%2FAppsV2_UpdateAssignmentRuleAsync """
    "assignments": [
        {
            "priority": 1,
            "distribution": {
                "name": "Text value",
                "description": "Text value",
                "smart_groups": ["c687ab4d-6c3b-485b-b30b-f47ff1132a4d"],
                "bsp_assignments": {
                    "smart_groups_online_licenses": ["3915d8a1-4e0c-4716-b1a5-6d7d391c020b"],
                    "smart_groups_offline_licenses": ["6bf7ab67-7065-4028-bef7-ee8d987a7c29"],
                },
                "vpp_app_details": {
                    "license_usage": [
                        {
                            "smart_group_uuid": "1a4caacd-bce7-4f7f-a257-0ea7967a349f",
                            "allocated": 10,
                            "redeemed": 3,
                        }
                    ]
                },
                "app_delivery_method": "AUTO",
                "pre_release_version": 0,
                "app_track_id": "Text value",
                "effective_date": "2022-12-02T12:07:07.5048189+00:00",
                "auto_update_devices_with_previous_versions": "true",
                "display_in_app_catalog": "true",
                "requires_approval": "true",
                "hide_notifications": "false",
                "application_transforms": ["5a4ec270-3245-41bb-b918-f2a97c2792d1"],
                "installer_deferral_allowed": "false",
                "deferral_type": "NoDeferral",
                "installer_deferral_interval": 2,
                "uem_deferral_interval": "FifteenMinutes",
                "installer_deferral_exit_code": "60012,6900",
                "max_deferral_count": 1,
                "is_default_assignment": "true",
                "reboot_override": "true",
                "msi_deployment_override_params": {
                    "device_restart": 1,
                    "installer_reboot_exit_code": "Text value",
                    "installer_success_exit_code": "Text value",
                    "restart_deadline_in_days": 1,
                },
                "keep_app_updated_automatically": "false",
                "auto_update_priority": "DEFAULT",
            },
            "restriction": {
                "remove_on_unenroll": "true",
                "prevent_application_backup": "true",
                "make_app_mdm_managed": "true",
                "managed_access": "true",
                "desired_state_management": "true",
                "prevent_removal": "true",
            },
            "tunnel": {
                "per_app_vpn_profile_uuid": "047d2636-be16-4df0-8cac-507ed119f56c",
                "afw_per_app_vpn_profile_uuid": "d87efc5a-589a-4577-a7b0-ed38102655a3",
            },
            "application_configuration": [
                {
                    "key": "Text value",
                    "value": "Text value",
                    "type": "STRING",
                    "nested_configurations": [{"type": 0}],
                    "id": 1234,
                    "uuid": "9417ef85-a2db-459d-a635-ffe8072b485b",
                }
            ],
            "application_attributes": [{"type": 0}],
            "is_dynamic_template_saved": "true",
            "is_apple_education_assignment": "true",
            "is_android_enterprise_config_template": "true",
            "app_profiles_mapping": [
                {
                    "configuration_type": "UNKNOWN",
                    "profile_category": "UNKNOWN",
                    "device_profile_uuid": "8075ff20-1435-43b9-939b-1c3fd27431bc",
                }
            ],
        }
    ],
    "excluded_smart_groups": ["5d936f7f-dcf6-4dae-a5b0-1dbdddd04bc8"],
    "application_msi_deployment_params": {},
    "id": 1234,
    "uuid": "6e1347bb-7648-467a-ad80-0715c8153c22",
}
