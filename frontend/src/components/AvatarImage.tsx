import { useEffect, useState } from 'react';

interface AvatarImageProps {
  size?: number;
  speaking?: boolean;
  className?: string;
  src?: string; // default tries /interviewer.png, falls back to /interviewer.svg
}

export default function AvatarImage({
  size = 420,
  speaking = false,
  className,
  src = '/interviewer.png',
}: AvatarImageProps) {
  const [imgSrc, setImgSrc] = useState(src);

  useEffect(() => {
    setImgSrc(src);
  }, [src]);

  return (
    <div className={className} style={{ width: size, maxWidth: '90vw' }}>
      <img
        src={imgSrc}
        onError={() => {
          if (imgSrc !== '/interviewer.svg') setImgSrc('/interviewer.svg');
        }}
        alt="AI 面试官 菜鸟庆"
        draggable={false}
        className={[
          'w-full h-auto select-none object-contain drop-shadow-2xl',
          'transition-transform duration-300 ease-out',
          speaking ? 'scale-[1.03]' : 'scale-100',
        ].join(' ')}
        style={{ animation: 'cnq-bob 4s ease-in-out infinite' }}
      />
    </div>
  );
}
