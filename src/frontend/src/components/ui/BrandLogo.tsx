import Image from 'next/image';

/** The supplied LabelX wordmark is shared by login and the application shell. */
export function BrandLogo() {
  return (
    <span className="lx-brand-logo">
      <Image src="/labelx-logo.jpg" alt="LabelX" width={160} height={160} priority unoptimized />
    </span>
  );
}
