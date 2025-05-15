import React, { useEffect, useState } from "react";
import "./RecordingBars.css";

interface RecordingBarsProps {
  volumes?: number[]; // Array of 8 numbers between 0 and 1
  color?: string; // CSS color for the bars
  animate?: boolean; // If true, animate bars up and down
}

const NUM_BARS = 8;

const RecordingBars: React.FC<RecordingBarsProps> = ({ volumes, color = '#6c63ff', animate = false }) => {
  const [animatedVolumes, setAnimatedVolumes] = useState<number[]>(Array(NUM_BARS).fill(0.5));

  useEffect(() => {
    if (!animate) return;
    let frame = 0;
    const interval = setInterval(() => {
      // Animate each bar with a sine wave, different phase for each
      setAnimatedVolumes(
        Array(NUM_BARS)
          .fill(0)
          .map((_, i) => 0.5 + 0.35 * Math.sin(frame / 10 + (i * Math.PI) / 4))
      );
      frame++;
    }, 60);
    return () => clearInterval(interval);
  }, [animate]);

  const barHeights = animate ? animatedVolumes : (volumes || Array(NUM_BARS).fill(0.5));

  return (
    <div className="recording-bars-container">
      {barHeights.map((v, i) => (
        <div
          key={i}
          className="recording-bar"
          style={{ height: `${20 + v * 60}px`, '--bar-color': color } as React.CSSProperties}
        />
      ))}
    </div>
  );
};

export default RecordingBars; 