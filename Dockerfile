FROM ros:kilted-ros-base

# Install common message type packages and Python dependencies
RUN apt-get update && apt-get install -y \
    python3-pip \
    ros-kilted-sensor-msgs \
    ros-kilted-geometry-msgs \
    ros-kilted-nav-msgs \
    ros-kilted-std-msgs \
    ros-kilted-std-srvs \
    ros-kilted-action-msgs \
    ros-kilted-service-msgs \
    ros-kilted-example-interfaces \
    ros-kilted-rosidl-runtime-py \
    && rm -rf /var/lib/apt/lists/*

RUN pip3 install pyyaml paho-mqtt --break-system-packages

WORKDIR /monitor

COPY monitor/ /monitor/
COPY custom/ /monitor/custom/

CMD ["/bin/bash", "-c", "source /opt/ros/kilted/setup.bash && python3 monitor_node.py"]
