import React from 'react';

interface Props {
  size?: number;
  color?: string;
  className?: string;
}

export default function ShardFlowLogo({ size = 40, color = 'var(--ink-soft)', className }: Props) {
  return (
    <svg
      viewBox="0 0 48 48"
      width={size}
      height={size}
      className={className}
      style={{
        stroke: color,
        strokeWidth: 1.5,
        fill: 'none',
        strokeLinecap: 'round',
        strokeLinejoin: 'round',
        display: 'block',
      }}
    >
      {/* 外轮廓 - 菱形碎片 */}
      <path d="M24 4 L42 20 Q44 24 42 28 L24 44 Q20 46 16 44 L6 28 Q4 24 6 20 L16 4 Q20 2 24 4Z" />
      
      {/* 内部流动曲线 */}
      <path d="M12 18 Q20 12 24 20 Q28 28 36 22" />
      <path d="M12 30 Q20 24 24 32 Q28 40 36 34" opacity="0.5" />
      
      {/* 中心点缀 */}
      <circle cx="24" cy="24" r="2.5" />
      
      {/* 边缘高光点 */}
      <circle cx="24" cy="8" r="1" fill={color} stroke="none" />
      <circle cx="38" cy="24" r="1" fill={color} stroke="none" opacity="0.6" />
      <circle cx="10" cy="24" r="1" fill={color} stroke="none" opacity="0.6" />
    </svg>
  );
}
