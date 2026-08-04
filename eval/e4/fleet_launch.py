"""E4 fleet launch: two namespaced TB3 + Nav2 stacks with a single /clock bridge.

Derived from nav2_bringup's cloned_multi_tb3_simulation_launch.py,
tb3_simulation_launch.py, and nav2_minimal_tb3_sim's spawn_tb3.launch.py
(Apache-2.0), reduced to what E4 needs and fixed in one respect: with the
stock files, every robot's ros_gz parameter_bridge bridges the absolute
/clock topic, so a two-robot bringup has two /clock publishers. Interleaved
deliveries from two publishers make subscribers observe simulation time
jumping backwards, which clears TF buffers and aborts navigation goals at
random. Here the per-robot bridges use a config without the clock entry
(tb3_bridge_noclock.yaml) and a single dedicated clock bridge is started
alongside the Gazebo server.

Robot names and spawn poses are fixed to the E4 crossing-patrol scenario.

    ros2 launch eval/e4/fleet_launch.py world:=... map:=... params_file:=... \
        [use_rviz:=True] [autostart:=True]
"""

import os
import tempfile
from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import (AppendEnvironmentVariable, DeclareLaunchArgument,
                            ExecuteProcess, GroupAction,
                            IncludeLaunchDescription, OpaqueFunction,
                            RegisterEventHandler)
from launch.conditions import IfCondition
from launch.event_handlers import OnShutdown
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import Command, FindExecutable, LaunchConfiguration
from launch_ros.actions import Node

E4_DIR = os.path.dirname(os.path.abspath(__file__))

ROBOTS = [
    {'name': 'robot1', 'x': '-2.00', 'y': '-0.50', 'yaw': '0.00'},
    {'name': 'robot2', 'x': '2.50', 'y': '0.00', 'yaw': '3.14159'},
]


def generate_launch_description() -> LaunchDescription:
    bringup_dir = get_package_share_directory('nav2_bringup')
    launch_dir = os.path.join(bringup_dir, 'launch')
    sim_dir = get_package_share_directory('nav2_minimal_tb3_sim')

    world = LaunchConfiguration('world')
    map_yaml_file = LaunchConfiguration('map')
    params_file = LaunchConfiguration('params_file')
    autostart = LaunchConfiguration('autostart')
    use_rviz = LaunchConfiguration('use_rviz')

    declare_args = [
        DeclareLaunchArgument('world', description='Full path to world SDF'),
        DeclareLaunchArgument('map', description='Full path to map yaml'),
        DeclareLaunchArgument(
            'params_file',
            default_value=os.path.join(E4_DIR, 'nav2_params.yaml'),
            description='Nav2 parameters file shared by both robots',
        ),
        DeclareLaunchArgument('autostart', default_value='True'),
        DeclareLaunchArgument('use_rviz', default_value='False'),
        DeclareLaunchArgument(
            'rviz_config',
            default_value=os.path.join(
                bringup_dir, 'rviz', 'nav2_default_view.rviz'),
        ),
    ]

    set_env_vars_resources = AppendEnvironmentVariable(
        'GZ_SIM_RESOURCE_PATH', os.path.join(sim_dir, 'models'))
    set_env_vars_resources2 = AppendEnvironmentVariable(
        'GZ_SIM_RESOURCE_PATH', str(Path(os.path.join(sim_dir)).parent.resolve()))

    # Gazebo server (world SDF is a xacro file; see tb3_simulation_launch.py).
    world_sdf = tempfile.mktemp(prefix='nav2_e4_', suffix='.sdf')
    world_sdf_xacro = ExecuteProcess(
        cmd=['xacro', '-o', world_sdf, ['headless:=', 'False'], world])
    gazebo_server = ExecuteProcess(
        cmd=['gz', 'sim', '-r', '-s', world_sdf], output='screen')
    remove_temp_sdf_file = RegisterEventHandler(event_handler=OnShutdown(
        on_shutdown=[OpaqueFunction(function=lambda _: os.remove(world_sdf))]))

    # The single simulation clock bridge (the fix this file exists for).
    clock_bridge = Node(
        package='ros_gz_bridge',
        executable='parameter_bridge',
        name='clock_bridge',
        output='screen',
        arguments=['/clock@rosgraph_msgs/msg/Clock[gz.msgs.Clock'],
    )

    urdf = os.path.join(sim_dir, 'urdf', 'turtlebot3_waffle.urdf')
    with open(urdf, 'r') as infp:
        robot_description = infp.read()

    robot_groups = []
    for robot in ROBOTS:
        namespace = robot['name']
        remappings = [('/tf', 'tf'), ('/tf_static', 'tf_static')]
        robot_groups.append(GroupAction([
            Node(
                package='ros_gz_bridge',
                executable='parameter_bridge',
                namespace=namespace,
                parameters=[{
                    'config_file': os.path.join(
                        E4_DIR, 'tb3_bridge_noclock.yaml'),
                    'expand_gz_topic_names': True,
                    'use_sim_time': True,
                }],
                output='screen',
            ),
            Node(
                package='ros_gz_sim',
                executable='create',
                namespace=namespace,
                output='screen',
                arguments=[
                    '-name', robot['name'],
                    # E4 robot SDF: stock gz_waffle plus a primitive visual
                    # crossing the lidar scan plane, so the robots can see
                    # each other (see gz_waffle_visible.sdf.xacro).
                    '-string', Command([
                        FindExecutable(name='xacro'), ' ',
                        'namespace:=', namespace, ' ',
                        os.path.join(E4_DIR, 'gz_waffle_visible.sdf.xacro')]),
                    '-x', robot['x'], '-y', robot['y'], '-z', '0.01',
                    '-R', '0.00', '-P', '0.00', '-Y', robot['yaw']],
            ),
            Node(
                package='robot_state_publisher',
                executable='robot_state_publisher',
                name='robot_state_publisher',
                namespace=namespace,
                output='screen',
                parameters=[{
                    'use_sim_time': True,
                    'robot_description': robot_description,
                }],
                remappings=remappings,
            ),
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(
                    os.path.join(launch_dir, 'rviz_launch.py')),
                condition=IfCondition(use_rviz),
                launch_arguments={
                    'namespace': namespace,
                    'use_sim_time': 'True',
                    'rviz_config': LaunchConfiguration('rviz_config'),
                }.items(),
            ),
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(
                    os.path.join(launch_dir, 'bringup_launch.py')),
                launch_arguments={
                    'namespace': namespace,
                    'slam': 'False',
                    'map': map_yaml_file,
                    'use_sim_time': 'True',
                    'params_file': params_file,
                    'autostart': autostart,
                    'use_composition': 'True',
                    'use_respawn': 'False',
                    'use_keepout_zones': 'False',
                    'use_speed_zones': 'False',
                }.items(),
            ),
        ]))

    ld = LaunchDescription()
    for action in declare_args:
        ld.add_action(action)
    ld.add_action(set_env_vars_resources)
    ld.add_action(set_env_vars_resources2)
    ld.add_action(world_sdf_xacro)
    ld.add_action(gazebo_server)
    ld.add_action(remove_temp_sdf_file)
    ld.add_action(clock_bridge)
    for group in robot_groups:
        ld.add_action(group)
    return ld
