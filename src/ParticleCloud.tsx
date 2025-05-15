import React from "react";
import "./ParticleCloud.css";

const NUM_PARTICLES = 12;
const RADIUS = 28; // radius of the cloud
const PARTICLE_RADIUS = 5;

const ParticleCloud: React.FC = () => {
  // Arrange particles in a circle
  const particles = Array.from({ length: NUM_PARTICLES }).map((_, i) => {
    const angle = (2 * Math.PI * i) / NUM_PARTICLES;
    const x = RADIUS * Math.cos(angle) + 40; // center at (40,40)
    const y = RADIUS * Math.sin(angle) + 40;
    return (
      <circle
        key={i}
        className="particle"
        cx={x}
        cy={y}
        r={PARTICLE_RADIUS}
        fill="#6c63ff"
      />
    );
  });

  return (
    <div className="particle-cloud-container">
      <svg width={80} height={80} viewBox="0 0 80 80">
        <g className="cloud-breath">
          {particles}
        </g>
      </svg>
    </div>
  );
};

export default ParticleCloud; 