#include <jni.h>
#include "edgeai/EdgeModel.hpp"
#include "edgeai/Engine.hpp"
#include "edgeai/TernaryBackend.hpp"
#include <memory>
#include <mutex>
#include <string>

namespace {
std::mutex engine_mutex;

edgeai::Engine& engine() {
    static auto backend = std::make_shared<edgeai::TernaryBackend>(
        edgeai::make_demo_edge_model(16, 32));
    static edgeai::Engine instance(edgeai::Mode::Eco, ":memory:", backend);
    return instance;
}
}

extern "C" JNIEXPORT jstring JNICALL
Java_com_edgeai_smoke_MainActivity_nativeAsk(JNIEnv* env, jclass, jstring input) {
    if (!input) return env->NewStringUTF("Erro: prompt nulo");
    const char* chars = env->GetStringUTFChars(input, nullptr);
    if (!chars) return nullptr;
    std::string prompt(chars);
    env->ReleaseStringUTFChars(input, chars);

    try {
        std::lock_guard<std::mutex> lock(engine_mutex);
        auto response = engine().ask(prompt);
        std::string text = response.text;
        text += "\n\n[route=";
        text += edgeai::route_name(response.route);
        text += " neural=";
        text += response.neural_used ? "1" : "0";
        text += " loops=" + std::to_string(response.loops_used) + "]";
        return env->NewStringUTF(text.c_str());
    } catch (const std::exception& error) {
        std::string text = std::string("Erro: ") + error.what();
        return env->NewStringUTF(text.c_str());
    }
}
