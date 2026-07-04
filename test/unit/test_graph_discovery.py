from graph_discovery import filter_graph, parse_action_list_t


def test_filter_graph_hides_ros_infrastructure_resources():
    raw = {
        "topics": [
            {"name": "/parameter_events", "interface": "rcl_interfaces/msg/ParameterEvent"},
            {"name": "/rosout", "interface": "rcl_interfaces/msg/Log"},
            {"name": "/cmd_vel", "interface": "geometry_msgs/msg/Twist"},
            {
                "name": "/reset_pose/_service_event",
                "interface": "std_srvs/srv/Trigger_Event",
            },
            {
                "name": "/demo_fibonacci/_action/feedback",
                "interface": "example_interfaces/action/Fibonacci_FeedbackMessage",
            },
        ],
        "services": [
            {
                "name": "/ros2_monitor_graph_discovery/get_parameters",
                "interface": "rcl_interfaces/srv/GetParameters",
            },
            {
                "name": "/robot_node/list_parameters",
                "interface": "rcl_interfaces/srv/ListParameters",
            },
            {"name": "/reset_pose", "interface": "std_srvs/srv/Trigger"},
            {
                "name": "/demo_fibonacci/_action/send_goal",
                "interface": "example_interfaces/action/Fibonacci_SendGoal",
            },
        ],
        "actions": [
            {"name": "/navigate_to_pose", "interface": "nav2_msgs/action/NavigateToPose"}
        ],
    }

    filtered = filter_graph(raw)

    assert filtered["topics"] == [
        {"name": "/cmd_vel", "interface": "geometry_msgs/msg/Twist"}
    ]
    assert filtered["services"] == [
        {"name": "/reset_pose", "interface": "std_srvs/srv/Trigger"}
    ]
    assert filtered["actions"] == [
        {"name": "/navigate_to_pose", "interface": "nav2_msgs/action/NavigateToPose"}
    ]


def test_filter_graph_can_include_system_resources():
    raw = {
        "topics": [{"name": "/rosout", "interface": "rcl_interfaces/msg/Log"}],
        "services": [],
        "actions": [],
    }

    assert filter_graph(raw, include_system=True) == raw


def test_parse_action_list_t_output():
    assert parse_action_list_t(
        """
        /demo_fibonacci [example_interfaces/action/Fibonacci]
        /navigate_to_pose [nav2_msgs/action/NavigateToPose]
        """
    ) == [
        {
            "name": "/demo_fibonacci",
            "interface": "example_interfaces/action/Fibonacci",
            "source_kind": "action",
        },
        {
            "name": "/navigate_to_pose",
            "interface": "nav2_msgs/action/NavigateToPose",
            "source_kind": "action",
        },
    ]
