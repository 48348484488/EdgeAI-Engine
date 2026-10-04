#include "edgeai/TransformerModel.hpp"
#include <iostream>

int main(int argc, char** argv) {
    if (argc != 2) {
        std::cerr << "usage: edgeai_low_resource_fixture OUTPUT.edge\n";
        return 2;
    }
    try {
        edgeai::make_transformer_demo(8, 12, 4).save(argv[1]);
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
