"""
GLSL 3.30 core-profile shader source strings.
"""

VERTEX_SRC = """
#version 330 core

layout(location = 0) in vec3 a_pos;
layout(location = 1) in vec2 a_uv;
layout(location = 2) in vec3 a_normal;

uniform mat4 u_model;
uniform mat4 u_view;
uniform mat4 u_proj;

out vec2  v_uv;
out vec3  v_normal;
out vec3  v_frag_pos;

void main() {
    vec4 world_pos = u_model * vec4(a_pos, 1.0);
    gl_Position    = u_proj * u_view * world_pos;
    v_uv           = a_uv;
    v_normal       = mat3(transpose(inverse(u_model))) * a_normal;
    v_frag_pos     = world_pos.xyz;
}
"""

FRAGMENT_SRC = """
#version 330 core

in vec2  v_uv;
in vec3  v_normal;
in vec3  v_frag_pos;

uniform sampler2D u_texture;
uniform vec3      u_light_dir;   // pre-normalised world-space key light
uniform float     u_ambient;     // base ambient
uniform bool      u_is_base;     // true = base skin layer, false = armor overlay
uniform bool      u_use_flat;    // true = ignore texture, use u_flat_color instead
uniform vec4      u_flat_color;  // flat colour used when u_use_flat is true

out vec4 frag_color;

void main() {
    vec4 tex;

    if (u_use_flat) {
        // Stand geometry: solid flat colour, no texture lookup
        tex = u_flat_color;
    } else if (u_is_base) {
        tex = texture(u_texture, v_uv);
        // Base layer: transparent pixels show as white so the character
        // always looks solid (erasing reveals white, not background).
        tex = mix(vec4(1.0, 1.0, 1.0, 1.0), tex, tex.a);
        tex.a = 1.0;
    } else {
        tex = texture(u_texture, v_uv);
        // Armor overlay: discard transparent pixels so the base shows through.
        if (tex.a < 0.01) discard;
    }

    vec3 n = normalize(v_normal);

    // Key light (front-top-right)
    float key  = max(dot(n, u_light_dir), 0.0);
    // Soft fill light from the opposite side so back faces aren't black
    float fill = max(dot(n, -u_light_dir), 0.0) * 0.3;

    float light = u_ambient + (1.0 - u_ambient) * (key + fill);
    light = clamp(light, 0.0, 1.0);
    frag_color  = vec4(tex.rgb * light, tex.a);
}
"""
