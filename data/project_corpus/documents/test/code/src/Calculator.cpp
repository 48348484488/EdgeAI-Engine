#include "edgeai/Calculator.hpp"
#include <cmath>
#include <iomanip>
#include <sstream>
#include <stdexcept>
namespace edgeai {
namespace {
class Parser {
public:
    explicit Parser(const std::string& input) : input_(input) {}
    double parse() {
        const double value = expression();
        whitespace();
        if (index_ != input_.size()) throw std::runtime_error("invalid expression");
        if (!std::isfinite(value)) throw std::runtime_error("nonfinite result");
        return value;
    }
private:
    const std::string& input_;
    std::size_t index_ = 0;
    void whitespace() {
        while (index_ < input_.size() && (input_[index_] == ' ' || input_[index_] == '\t')) ++index_;
    }
    bool eat(char c) {
        whitespace();
        if (index_ < input_.size() && input_[index_] == c) { ++index_; return true; }
        return false;
    }
    double expression() {
        double value = term();
        for (;;) {
            if (eat('+')) value += term();
            else if (eat('-')) value -= term();
            else return value;
        }
    }
    double term() {
        double value = unary();
        for (;;) {
            if (eat('*')) value *= unary();
            else if (eat('/')) {
                const double denominator = unary();
                if (denominator == 0) throw std::runtime_error("division by zero");
                value /= denominator;
            } else if (eat('%')) {
                const double denominator = unary();
                if (denominator == 0) throw std::runtime_error("modulo by zero");
                value = std::fmod(value, denominator);
            } else return value;
        }
    }
    double unary() {
        if (eat('+')) return unary();
        if (eat('-')) return -unary();
        return power();
    }
    double power() {
        const double value = primary();
        whitespace();
        bool exponent = eat('^');
        if (!exponent && index_ + 1 < input_.size() && input_[index_] == '*' && input_[index_ + 1] == '*') {
            index_ += 2;
            exponent = true;
        }
        if (!exponent) return value;
        // Right-associative exponentiation binds more strongly than unary minus.
        const double degree = unary();
        if (!std::isfinite(degree) || std::abs(degree) > 32) throw std::runtime_error("exponent too large");
        return std::pow(value, degree);
    }
    double primary() {
        whitespace();
        if (eat('(')) {
            const double value = expression();
            if (!eat(')')) throw std::runtime_error("missing closing parenthesis");
            return value;
        }
        const auto start = index_;
        bool dot = false;
        while (index_ < input_.size()) {
            const char c = input_[index_];
            if (c >= '0' && c <= '9') { ++index_; continue; }
            if (c == '.' && !dot) { dot = true; ++index_; continue; }
            break;
        }
        if (start == index_) throw std::runtime_error("number expected");
        return std::stod(input_.substr(start, index_ - start));
    }
};
}
double calculate(const std::string& expression) {
    if (expression.size() > 512) throw std::runtime_error("expression too long");
    return Parser(expression).parse();
}
std::string format_number(double value) {
    std::ostringstream out;
    out << std::setprecision(15) << value;
    return out.str();
}
}
