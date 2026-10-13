import Image from 'next/image';

export function BrandMark({ inverse = false, large = false }: { inverse?: boolean; large?: boolean }) {
  return (
    <span className={`lx-brandmark${inverse ? ' lx-brandmark--inverse' : ''}${large ? ' lx-brandmark--large' : ''}`}
      role="img" aria-label="LabelX">
      <Image className="lx-brandmark__image" src="/labelx-logo.png" alt="" width={2000} height={2000} unoptimized />
      {inverse && <Image className="lx-brandmark__image lx-brandmark__red" src="/labelx-logo.png" alt="" width={2000} height={2000} unoptimized />}
    </span>
  );
}
