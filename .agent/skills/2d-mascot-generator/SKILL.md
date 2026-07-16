---
name: 2D Live Mascot Generator
description: Generates, keys, and animates a 2D mascot avatar based on project brand guidelines and input animations.
---

### Objective
When the user asks to "generate a mascot," "create a live avatar," or animate your character, execute this skill.

### Capabilities
1. **Contextual Analysis:** Read the `gemini.md` or `brand_guidelines.md` in the project to extract brand colors, tone, and character style.
2. **Asset Generation:** Use your built-in image tools (e.g., NanoBanana) to generate distinct expressions and poses.
3. **Animation/Integration:** Set up the sprite sheet or integrate with animation frameworks (like Lottie or Remotion) to provide a live, moving mascot for the web application.

### Instructions for the Agent
1. Find and parse any existing brand guideline files in the project.
2. Generate base images of the mascot.
3. Automatically configure the necessary HTML, CSS, or React components to embed the living mascot in the hero or footer of the user's project.


### Animation Capabilities
1. **State Management:** Map user interactions (idle, hovering, clicking, typing) to specific mascot animations.
2. **Sprite-Sheet Splitting:** Slice a generated image grid into individual CSS keyframe steps or canvas-rendered frames.
3. **Rigging Instructions:** Generate JSON vectors or layout maps to feed into third-party web animators (Rive, Lottie, or Framer Motion).

### Execution Rules for Animation
- **Rule 1:** When a user requests a new animation (e.g., "make the mascot wave"), check the asset folder for an existing sprite sheet or layer map.
- **Rule 2:** If layers exist, generate a custom React/CSS component to cycle frames. 
- **Rule 3:** If layers do not exist, use the image tool to generate sequential frames (Frame 0 to Frame 5) keeping the background transparent (`#00000000` or alpha layer).
