import { useEffect, useState } from 'react';
import CountUp from 'react-countup';
import { motion } from 'framer-motion';

interface AnimatedCounterProps {
  value: number;
  duration?: number;
  prefix?: string;
  suffix?: string;
  className?: string;
  decimals?: number;
}

export function AnimatedCounter({
  value,
  duration = 2,
  prefix = '',
  suffix = '',
  className = '',
  decimals = 0
}: AnimatedCounterProps) {
  const [prevValue, setPrevValue] = useState(value);
  const [isIncreasing, setIsIncreasing] = useState(false);

  useEffect(() => {
    if (value > prevValue) {
      setIsIncreasing(true);
    } else if (value < prevValue) {
      setIsIncreasing(false);
    }
    setPrevValue(value);
  }, [value, prevValue]);

  return (
    <motion.div
      className={className}
      animate={{
        scale: value !== prevValue ? [1, 1.1, 1] : 1,
        color: isIncreasing ? '#10B981' : value < prevValue ? '#F43F5E' : undefined
      }}
      transition={{ duration: 0.3 }}
    >
      <CountUp
        start={prevValue}
        end={value}
        duration={duration}
        decimals={decimals}
        prefix={prefix}
        suffix={suffix}
        preserveValue
      />
    </motion.div>
  );
}