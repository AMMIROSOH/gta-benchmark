cmake_minimum_required(VERSION 3.20)
project(gta-benchmark LANGUAGES CXX)

if(NOT MSVC OR NOT CMAKE_SIZEOF_VOID_P EQUAL 4)
  message(FATAL_ERROR "Build with the existing MSVC compiler and -A Win32.")
endif()
set(PLUGIN_SDK_DIR "D:/SA-Agent/dependencies/plugin-sdk" CACHE PATH "Plugin-SDK checkout")
if(NOT EXISTS "${PLUGIN_SDK_DIR}/output/lib/Plugin.lib")
  message(FATAL_ERROR "Build the Plugin-SDK San Andreas Release library first.")
endif()

add_library(SAAgentTelemetry SHARED src/telemetry.cpp src/actors.cpp src/agent_bridge.cpp src/navigation.cpp src/lifecycle.cpp src/telemetry.def)
set_target_properties(SAAgentTelemetry PROPERTIES
  PREFIX "" SUFFIX ".asi"
  MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
target_compile_features(SAAgentTelemetry PRIVATE cxx_std_23)
target_compile_definitions(SAAgentTelemetry PRIVATE
  GTASA PLUGIN_SGV_10US RW WIN32_LEAN_AND_MEAN NOMINMAX
  _CRT_SECURE_NO_WARNINGS _CRT_NON_CONFORMING_SWPRINTFS)
target_include_directories(SAAgentTelemetry SYSTEM PRIVATE
  "${PLUGIN_SDK_DIR}/plugin_sa"
  "${PLUGIN_SDK_DIR}/plugin_sa/game_sa"
  "${PLUGIN_SDK_DIR}/plugin_sa/game_sa/enums"
  "${PLUGIN_SDK_DIR}/plugin_sa/game_sa/rw"
  "${PLUGIN_SDK_DIR}/shared"
  "${PLUGIN_SDK_DIR}/shared/game"
  "${PLUGIN_SDK_DIR}/shared/dxsdk"
  "${PLUGIN_SDK_DIR}/safetyhook")
target_compile_options(SAAgentTelemetry PRIVATE /W4 /EHsc)
target_link_libraries(SAAgentTelemetry PRIVATE
  "${PLUGIN_SDK_DIR}/output/lib/Plugin.lib" psapi)

include(CTest)
if(BUILD_TESTING)
  add_executable(SAAgentMovementTest tests/native_movement.cpp)
  target_compile_features(SAAgentMovementTest PRIVATE cxx_std_17)
  add_test(NAME world_direction_camera_projection COMMAND SAAgentMovementTest)
  add_executable(SAAgentKillTest tests/native_kills.cpp)
  target_compile_features(SAAgentKillTest PRIVATE cxx_std_17)
  add_test(NAME attributed_kill_lifetimes COMMAND SAAgentKillTest)
endif()
