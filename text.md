```
import React, { useState } from 'react';
import { motion } from 'framer-motion';
import { Github } from 'lucide-react';

export default function MagneticButton() {
  const [isHovered, setIsHovered] = useState(false);
  const [mouseCoords, setMouseCoords] = useState({ x: 0, y: 0 });

  const handleMouseMove = (e: React.MouseEvent<HTMLButtonElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const x = e.clientX - rect.left - rect.width / 2;
    const y = e.clientY - rect.top - rect.height / 2;
    setMouseCoords({ x: x * 0.35, y: y * 0.35 });
  };

  const handleMouseLeave = () => {
    setIsHovered(false);
    setMouseCoords({ x: 0, y: 0 });
  };

  return (
    <motion.button
      onMouseEnter={() => setIsHovered(true)}
      onMouseMove={handleMouseMove}
      onMouseLeave={handleMouseLeave}
      animate={{
        x: isHovered ? mouseCoords.x : 0,
        y: isHovered ? mouseCoords.y : 0
      }}
      whileTap={{ scale: 0.96 }}
      className="relative flex items-center justify-center text-white h-[36px] px-6 rounded-[40px] bg-white/[0.04] hover:bg-white/[0.06] border border-white/5 cursor-pointer transition-colors duration-150"
    >
      <Github className="w-4 h-4 mr-2.5" />
      <span className="font-medium tracking-tight text-[13px]">Magnetic Field</span>
    </motion.button>
  );
}
```

