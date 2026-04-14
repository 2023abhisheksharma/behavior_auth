cmake_minimum_required(VERSION 3.16)
project(LinuxEventEngine)

set(CMAKE_CXX_STANDARD 17)

find_package(PkgConfig REQUIRED)
pkg_check_modules(LIBEVDEV REQUIRED libevdev)

pkg_check_modules(ZMQ REQUIRED libzmq)

include_directories(
    include
    ${LIBEVDEV_INCLUDE_DIRS}
    ${ZMQ_INCLUDE_DIRS}
)

file(GLOB SOURCES "src/*.cpp")

add_executable(event_engine ${SOURCES})

target_link_libraries(event_engine
    ${LIBEVDEV_LIBRARIES}
    ${ZMQ_LIBRARIES}
)
