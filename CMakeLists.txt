cmake_minimum_required(VERSION 3.16)
project(EdgeAIEngine VERSION 0.16.0 LANGUAGES CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
if(MSVC)
  # Keep source and execution character sets deterministic. The project contains
  # UTF-8 route strings/tests and must not depend on the runner's active code page.
  add_compile_options(/utf-8)
endif()
option(EDGEAI_DISABLE_SIMD "Force portable kernels" OFF)
if(EDGEAI_DISABLE_SIMD)
  add_compile_definitions(EDGEAI_DISABLE_SIMD)
endif()
option(EDGEAI_SANITIZERS "Address + undefined-behavior sanitizers" OFF)
if(EDGEAI_SANITIZERS AND NOT MSVC)
  add_compile_options(-fsanitize=address,undefined -fno-omit-frame-pointer)
  add_link_options(-fsanitize=address,undefined)
endif()
option(EDGEAI_BUILD_TESTS "Build tests" ON)
option(EDGEAI_BUILD_BENCHMARK "Build benchmarks" ON)
option(EDGEAI_LOW_RESOURCE "Build the focused CPU-only runtime" OFF)
add_library(edgeai
    src/CodeSearch.cpp src/Engine.cpp src/Router.cpp src/Calculator.cpp src/TextTools.cpp src/Memory.cpp src/Scheduler.cpp src/Hardware.cpp src/Backend.cpp
    src/HybridMemory.cpp src/HybridModel.cpp src/HybridBackend.cpp
    src/ByteBPE.cpp src/TransformerModel.cpp src/TransformerBackend.cpp
    src/MixedMatrix.cpp src/Int8Kernel.cpp src/Ternary.cpp src/Kernels.cpp src/EdgeModel.cpp src/TernaryBackend.cpp
)
target_include_directories(edgeai PUBLIC include)

set(EDGEAI_LOW_RESOURCE_SOURCES
    src/BoundedMemory.cpp
    src/LowResourceEngine.cpp
    src/LowResourceMetrics.cpp
    src/Router.cpp
    src/Calculator.cpp
    src/TextTools.cpp
    src/Backend.cpp
    src/ByteBPE.cpp
    src/TransformerModel.cpp
    src/TransformerBackend.cpp
    src/MixedMatrix.cpp
    src/Int8Kernel.cpp
    src/Ternary.cpp
    src/Kernels.cpp
)
if(EDGEAI_LOW_RESOURCE)
  add_library(edgeai_low_resource ${EDGEAI_LOW_RESOURCE_SOURCES})
  target_include_directories(edgeai_low_resource PUBLIC include)
  if(MSVC)
    target_compile_options(edgeai_low_resource PRIVATE /W4)
  else()
    target_compile_options(edgeai_low_resource PRIVATE -Wall -Wextra -Wpedantic)
  endif()
  add_executable(edgeai_low_resource_cli examples/low_resource.cpp)
  target_link_libraries(edgeai_low_resource_cli PRIVATE edgeai_low_resource)
  add_executable(edgeai_low_resource_fixture tools/make_low_resource_fixture.cpp)
  target_link_libraries(edgeai_low_resource_fixture PRIVATE edgeai_low_resource)
  if(EDGEAI_BUILD_TESTS)
    enable_testing()
    add_executable(edgeai_test_bounded_memory tests/test_bounded_memory.cpp)
    target_link_libraries(edgeai_test_bounded_memory PRIVATE edgeai_low_resource)
    add_test(NAME edgeai_bounded_memory COMMAND edgeai_test_bounded_memory)
    add_executable(edgeai_test_low_resource_engine tests/test_low_resource_engine.cpp)
    target_link_libraries(edgeai_test_low_resource_engine PRIVATE edgeai_low_resource)
    add_test(NAME edgeai_low_resource_engine COMMAND edgeai_test_low_resource_engine)
  endif()
endif()

if(ANDROID)
  add_library(edgeai_android_jni SHARED android/app/src/main/cpp/jni.cpp)
  target_link_libraries(edgeai_android_jni PRIVATE edgeai)
  target_include_directories(edgeai_android_jni PRIVATE include)
endif()
if(MSVC)
  target_compile_options(edgeai PRIVATE /W4)
else()
  target_compile_options(edgeai PRIVATE -Wall -Wextra -Wpedantic)
endif()
add_executable(edgeai_chat examples/chat.cpp)
target_link_libraries(edgeai_chat PRIVATE edgeai)
add_executable(edgeai_make_demo tools/make_demo_model.cpp)
target_link_libraries(edgeai_make_demo PRIVATE edgeai)
add_executable(edgeai_logits tools/logits.cpp)
target_link_libraries(edgeai_logits PRIVATE edgeai)
add_executable(edgeai_evaluate tools/evaluate.cpp)
target_link_libraries(edgeai_evaluate PRIVATE edgeai)
add_executable(edgeai_inspect tools/inspect_model.cpp)
target_link_libraries(edgeai_inspect PRIVATE edgeai)
foreach(tool code_search tokenize text_eval generate token_logits)
  add_executable(edgeai_${tool} tools/${tool}.cpp)
  target_link_libraries(edgeai_${tool} PRIVATE edgeai)
endforeach()
if(EDGEAI_BUILD_TESTS)
  enable_testing()
  add_executable(edgeai_tests tests/test_engine.cpp)
  target_link_libraries(edgeai_tests PRIVATE edgeai)
  add_test(NAME edgeai_tests COMMAND edgeai_tests)
  add_executable(edgeai_regressions tests/test_regressions.cpp)
  target_link_libraries(edgeai_regressions PRIVATE edgeai)
  add_test(NAME edgeai_regressions COMMAND edgeai_regressions)
  foreach(test code_search code_cache memory kernels hybrid tools precision transformer bpe instruction)
    add_executable(edgeai_test_${test} tests/test_${test}.cpp)
    target_link_libraries(edgeai_test_${test} PRIVATE edgeai)
    add_test(NAME edgeai_${test} COMMAND edgeai_test_${test})
  endforeach()
endif()
if(EDGEAI_BUILD_BENCHMARK)
  add_executable(edgeai_benchmark benchmarks/benchmark.cpp)
  target_link_libraries(edgeai_benchmark PRIVATE edgeai)
  add_executable(edgeai_runtime_benchmark benchmarks/runtime.cpp)
  target_link_libraries(edgeai_runtime_benchmark PRIVATE edgeai)
  add_executable(edgeai_matrix_benchmark benchmarks/ternary_vs_dense.cpp)
  target_link_libraries(edgeai_matrix_benchmark PRIVATE edgeai)
endif()

if(EDGEAI_BUILD_TESTS AND TARGET edgeai_runtime_benchmark)
  find_package(Python3 COMPONENTS Interpreter QUIET)
  if(Python3_Interpreter_FOUND)
    add_test(NAME edgeai_runtime_cli COMMAND ${Python3_EXECUTABLE}
      ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_runtime_cli.py $<TARGET_FILE:edgeai_runtime_benchmark>)
    add_test(NAME edgeai_inspect_cli COMMAND ${Python3_EXECUTABLE}
      ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_inspect_cli.py $<TARGET_FILE:edgeai_inspect>)
    add_test(NAME edgeai_chat_banner COMMAND ${Python3_EXECUTABLE}
      ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_chat_banner.py $<TARGET_FILE:edgeai_chat>)
  endif()
endif()

# Exact v0.9 search source retained as a benchmark, not linked into the engine.
if(EDGEAI_BUILD_BENCHMARK)
  add_executable(edgeai_code_search_v09_baseline
    benchmarks/v09_baseline/CodeSearch.cpp benchmarks/v09_baseline/batch.cpp)
  target_include_directories(edgeai_code_search_v09_baseline PRIVATE benchmarks/v09_baseline/include)
endif()

