#pragma once
// Portable CPU linear-blend skinning kernel for 4x4 row-major float matrices.
// Matrices are stored contiguously, with a stride of 16 floats per bone.
// Weighted matrix blending is algebraically equivalent to per-influence
// position/normal transforms, up to floating-point reassociation error.
// This is a generic kernel: no Unity, raylib or Last Island dependencies.
#include <cmath>
#include <cstddef>
#include <cstdint>

namespace edgeai_lbs {
inline void skin_vertex(const float* matrices16, const std::uint16_t* paletteIndices,
                        const float* weights, int influenceCount,
                        const float* position, const float* normal,
                        float* outputPosition, float* outputNormal) {
    float blended[12] = {};
    for (int influence = 0; influence < influenceCount; ++influence) {
        const float weight = weights[influence];
        if (weight <= 0.0f) continue;
        const float* m = matrices16 + std::size_t(paletteIndices[influence]) * 16;
        for (int row = 0; row < 3; ++row) {
            const int offset = row * 4;
            blended[offset]     += weight * m[offset];
            blended[offset + 1] += weight * m[offset + 1];
            blended[offset + 2] += weight * m[offset + 2];
            blended[offset + 3] += weight * m[offset + 3];
        }
    }
    const float x = position[0], y = position[1], z = position[2];
    const float nx = normal[0], ny = normal[1], nz = normal[2];
    for (int row = 0; row < 3; ++row) {
        const int k = row * 4;
        outputPosition[row] = blended[k] * x + blended[k+1] * y +
                              blended[k+2] * z + blended[k+3];
        outputNormal[row] = blended[k] * nx + blended[k+1] * ny +
                            blended[k+2] * nz;
    }
    const float norm = std::sqrt(outputNormal[0]*outputNormal[0] +
                                 outputNormal[1]*outputNormal[1] +
                                 outputNormal[2]*outputNormal[2]);
    if (norm > 1.0e-7f) {
        outputNormal[0] /= norm;
        outputNormal[1] /= norm;
        outputNormal[2] /= norm;
    }
}
}  // namespace edgeai_lbs
