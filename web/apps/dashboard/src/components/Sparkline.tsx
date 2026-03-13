interface SparklineProps {
  data: number[];
  width?: number;
  height?: number;
  className?: string;
  color?: string;
}

export function Sparkline({
  data,
  width = 80,
  height = 28,
  className,
  color,
}: SparklineProps) {
  if (data.length < 2) {
    return <svg width={width} height={height} className={className} />;
  }

  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1; // flat-line guard: avoid division by zero

  const points = data
    .map((value, index) => {
      const x = (index / (data.length - 1)) * width;
      const y = height - ((value - min) / range) * (height - 4) - 2;
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(" ");

  return (
    <svg
      width={width}
      height={height}
      className={className}
      aria-hidden="true"
    >
      <polyline
        points={points}
        fill="none"
        strokeWidth="1.5"
        strokeLinejoin="round"
        strokeLinecap="round"
        stroke={color ?? "currentColor"}
        className={color ? undefined : "stroke-current"}
      />
    </svg>
  );
}
