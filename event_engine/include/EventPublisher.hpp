#pragma once
#include <zmq.hpp>
#include <string>
#include <mutex>

class EventPublisher {
private:
    zmq::context_t context;
    zmq::socket_t socket;
    std::mutex mtx;

public:
    EventPublisher(const std::string& address);
    void publish(const std::string& msg);
};