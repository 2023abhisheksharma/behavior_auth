#include "EventEngine.hpp"
#include <iostream>

int main() {
    std::cout << "Linux Event Engine Running...\n";

    EventEngine engine;
    engine.run();

    return 0;
}
