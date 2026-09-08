cmake_minimum_required(VERSION 3.16)
project(ChronosEventEngine)

set(CMAKE_CXX_STANDARD 17)

find_package(ZeroMQ REQUIRED)
find_package(cppzmq REQUIRED)

include_directories(include)

if(WIN32)
    add_executable(event_engine src/main.cpp src/EventEngine_Windows.cpp src/EventPublisher.cpp)
else()
    find_package(PkgConfig REQUIRED)
    pkg_check_modules(LIBEVDEV REQUIRED libevdev)
    include_directories(${LIBEVDEV_INCLUDE_DIRS})
    add_executable(event_engine src/main.cpp src/EventEngine.cpp src/EventPublisher.cpp)
    target_link_libraries(event_engine PRIVATE ${LIBEVDEV_LIBRARIES})
endif()

target_link_libraries(event_engine PRIVATE cppzmq)
