"use client";

import { useEffect, useRef } from "react";
import { motion } from "framer-motion";

interface Particle {
  id: number;
  x: number;
  y: number;
  size: number;
  duration: number;
  delay: number;
  type: "dust" | "petal" | "sparkle";
}

export function AmbientParticles() {
  const particles: Particle[] = Array.from({ length: 30 }, (_, i) => ({
    id: i,
    x: Math.random() * 100,
    y: Math.random() * 100,
    size: Math.random() * 4 + 2,
    duration: Math.random() * 20 + 15,
    delay: Math.random() * 10,
    type: i % 5 === 0 ? "petal" : i % 3 === 0 ? "sparkle" : "dust",
  }));

  return (
    <div className="fixed inset-0 pointer-events-none overflow-hidden z-50">
      {particles.map((particle) => (
        <motion.div
          key={particle.id}
          className={`absolute rounded-full ${
            particle.type === "petal"
              ? "bg-blossom/30"
              : particle.type === "sparkle"
              ? "bg-gold/40"
              : "bg-parchment/20"
          }`}
          style={{
            left: `${particle.x}%`,
            width: particle.size,
            height: particle.size,
            filter: particle.type === "sparkle" ? "blur(0.5px)" : "blur(1px)",
          }}
          initial={{ y: "100vh", opacity: 0, rotate: 0 }}
          animate={{
            y: "-100vh",
            opacity: [0, 0.8, 0.8, 0],
            rotate: particle.type === "petal" ? 720 : 360,
            x: [0, Math.sin(particle.id) * 50, 0],
          }}
          transition={{
            duration: particle.duration,
            delay: particle.delay,
            repeat: Infinity,
            ease: "linear",
          }}
        />
      ))}
    </div>
  );
}

export function CandlelightGlow() {
  return (
    <div className="fixed inset-0 pointer-events-none z-0">
      {/* Main ambient glow */}
      <motion.div
        className="absolute top-0 left-1/4 w-96 h-96 rounded-full"
        style={{
          background: "radial-gradient(circle, rgba(180,140,80,0.15) 0%, transparent 70%)",
        }}
        animate={{
          opacity: [0.5, 0.7, 0.5],
          scale: [1, 1.1, 1],
        }}
        transition={{
          duration: 4,
          repeat: Infinity,
          ease: "easeInOut",
        }}
      />
      
      {/* Secondary glow - right side */}
      <motion.div
        className="absolute top-1/4 right-0 w-80 h-80 rounded-full"
        style={{
          background: "radial-gradient(circle, rgba(200,120,150,0.1) 0%, transparent 70%)",
        }}
        animate={{
          opacity: [0.4, 0.6, 0.4],
          scale: [1, 1.05, 1],
        }}
        transition={{
          duration: 5,
          repeat: Infinity,
          ease: "easeInOut",
          delay: 1,
        }}
      />

      {/* Bottom ambient */}
      <motion.div
        className="absolute bottom-0 left-1/2 -translate-x-1/2 w-full h-64"
        style={{
          background: "linear-gradient(to top, rgba(100,60,40,0.2) 0%, transparent 100%)",
        }}
        animate={{
          opacity: [0.6, 0.8, 0.6],
        }}
        transition={{
          duration: 6,
          repeat: Infinity,
          ease: "easeInOut",
        }}
      />

      {/* Vignette effect */}
      <div 
        className="absolute inset-0"
        style={{
          background: "radial-gradient(ellipse at center, transparent 40%, rgba(10,8,6,0.6) 100%)",
        }}
      />
    </div>
  );
}
