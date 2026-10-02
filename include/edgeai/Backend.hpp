#pragma once
#include "Types.hpp"
#include <memory>
#include <string>
namespace edgeai {
class IModelBackend {
public:
    virtual ~IModelBackend() = default;
    virtual std::string name() const = 0;
    virtual bool available() const = 0;
    virtual Response infer(const std::string& prompt, const Budget& budget) = 0;
};
class NullBackend final : public IModelBackend {
public:
    std::string name() const override { return "null"; }
    bool available() const override { return false; }
    Response infer(const std::string& prompt, const Budget& budget) override;
};
class EchoReasonerBackend final : public IModelBackend {
public:
    std::string name() const override { return "echo-reasoner-dev"; }
    bool available() const override { return true; }
    Response infer(const std::string& prompt, const Budget& budget) override;
};
using BackendPtr = std::shared_ptr<IModelBackend>;
}
