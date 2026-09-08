#include "EventEngine.hpp"
#include <iostream>

int main() {
#ifdef _WIN32
    std::cout << "Windows Event Engine Running...\n";
#else
    std::cout << "Linux Event Engine Running...\n";
#endif

    EventEngine engine;
    engine.run();

    return 0;
}
