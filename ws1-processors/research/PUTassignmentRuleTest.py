assignment_rules = {
    "assignments": [
        {
            "priority": 0,
            "distribution": {
                "name": "TESTING",
                "description": "Early Access for new software versions - macOS-SW-EARLY_ACCESS",
                "smart_groups": [
                    "12345678-0565-49f6-9ad9-5d5187087d3c",
                    "12345678-6b7a-4942-8c8a-296a907ebf23",
                ],
                "app_delivery_method": "On_Demand",
                "effective_date": "2023-02-21T12:00:00.0+00:00",
                "auto_update_devices_with_previous_versions": "true",
                "display_in_app_catalog": "true",
                "is_default_assignment": "true",
                "keep_app_updated_automatically": "true",
            },
            "restriction": {
                "remove_on_unenroll": "false",
                "managed_access": "false",
                "desired_state_management": "false",
                "prevent_removal": "false",
            },
        },
        {
            "priority": 1,
            "distribution": {
                "name": "PRODUCTION",
                "description": "On-Demand for macOS setup groups VIP, Marketing",
                "smart_groups": [
                    "12345678-9e37-4b14-9913-d55d332467c3",
                    "12345678-40fd-4ce4-8faf-16204e9da228",
                ],
                "app_delivery_method": "On_Demand",
                "effective_date": "2023-02-21T12:00:00.0+00:00",
                "auto_update_devices_with_previous_versions": "true",
                "display_in_app_catalog": "true",
                "is_default_assignment": "false",
                "keep_app_updated_automatically": "true",
            },
            "restriction": {
                "remove_on_unenroll": "false",
                "managed_access": "false",
                "desired_state_management": "false",
                "prevent_removal": "false",
            },
        },
    ]
}
