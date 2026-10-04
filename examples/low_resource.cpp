#include "edgeai/LowResourceEngine.hpp"
#include "edgeai/LowResourceMetrics.hpp"
#include "edgeai/Types.hpp"
#include <iostream>
#include <stdexcept>
#include <string>
#include <chrono>
#include <fstream>
#include <vector>

namespace {
std::string escape_json(const std::string& input) {
    std::string out;
    for (const char c : input) {
        if (c == '\\' || c == '"') { out += '\\'; out += c; }
        else if (c == '\n') out += "\\n";
        else if (static_cast<unsigned char>(c) >= 0x20) out += c;
    }
    return out;
}
}

int main(int argc, char** argv) {
    try {
        const auto started = std::chrono::steady_clock::now();
        edgeai::LowResourceConfig config;
        std::string prompt;
        std::string metrics_path;
        std::string workload_path;
        for (int i = 1; i < argc; ++i) {
            const std::string arg = argv[i];
            auto value = [&](const char* name) -> std::string {
                if (i + 1 >= argc) throw std::invalid_argument(std::string("missing value for ") + name);
                return argv[++i];
            };
            if (arg == "--model") config.model_path = value("--model");
            else if (arg == "--memory") config.memory_path = value("--memory");
            else if (arg == "--threads") config.threads = static_cast<unsigned>(std::stoul(value("--threads")));
            else if (arg == "--prompt") prompt = value("--prompt");
            else if (arg == "--metrics-json") metrics_path = value("--metrics-json");
            else if (arg == "--workload") workload_path = value("--workload");
            else throw std::invalid_argument("unknown argument: " + arg);
        }
        if (config.model_path.empty()) throw std::invalid_argument("--model is required");
        const auto threads = config.threads;
        edgeai::LowResourceEngine engine(std::move(config));
        const auto startup_ms = static_cast<std::uint64_t>(std::chrono::duration_cast<std::chrono::milliseconds>(
            std::chrono::steady_clock::now() - started).count());
        std::vector<std::string> prompts;
        if (!workload_path.empty()) {
            std::ifstream input(workload_path);
            if (!input) throw std::invalid_argument("cannot open workload");
            std::string line;
            while (std::getline(input, line)) {
                if (line.size() > engine.limits().max_prompt_bytes) throw std::invalid_argument("workload prompt exceeds limit");
                if (!line.empty()) prompts.push_back(line);
            }
        } else {
            if (prompt.empty()) {
                char c = 0;
                while (std::cin.get(c) && c != '\n') {
                    if (prompt.size() == engine.limits().max_prompt_bytes) throw std::invalid_argument("prompt exceeds limit");
                    if (c != '\r') prompt.push_back(c);
                }
            }
            prompts.push_back(prompt);
        }
        for (const auto& item : prompts) {
            const auto response = engine.ask(item);
            std::cout << "{\"route\":\"" << edgeai::route_name(response.route)
                      << "\",\"neural_used\":" << (response.neural_used ? "true" : "false")
                      << ",\"text\":\"" << escape_json(response.text) << "\"}\n";
        }
        edgeai::LowResourceMetrics metrics;
#if defined(_WIN32)
        metrics.platform = "windows-x86_64";
#elif defined(__linux__)
        metrics.platform = "linux-x86_64";
#else
        metrics.platform = "unknown";
#endif
        metrics.startup_ms = startup_ms;
        metrics.model_file_bytes = engine.model_file_bytes();
        metrics.model_weight_bytes = engine.model_weight_bytes();
        metrics.state_payload_bytes = engine.state_payload_bytes();
        metrics.numeric_working_bytes = engine.numeric_working_bytes();
        metrics.memory_store_bytes = engine.memory_store_bytes();
        metrics.threads = threads;
        metrics.requests = prompts.size();
        edgeai::write_metrics_json(metrics_path, metrics);
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "edgeai-low-resource: " << error.what() << '\n';
        return 2;
    }
}
