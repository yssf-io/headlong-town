import clsx from 'clsx';
import { MouseEventHandler, ReactNode } from 'react';

export default function Button(props: {
  className?: string;
  href?: string;
  imgUrl: string;
  onClick?: MouseEventHandler;
  title?: string;
  /** Small enough to sit in the instrument rail (see TopBar). */
  compact?: boolean;
  children: ReactNode;
}) {
  return (
    <a
      className={clsx(
        'button text-white shadow-solid pointer-events-auto',
        props.compact ? 'text-sm' : 'text-xl',
        props.className,
      )}
      href={props.href}
      title={props.title}
      onClick={props.onClick}
    >
      <div className="inline-block bg-clay-700">
        <span>
          <div className={clsx('inline-flex h-full items-center', props.compact ? 'gap-2' : 'gap-4')}>
            <img
              className={clsx(props.compact ? 'w-4 h-4' : 'w-4 h-4 sm:w-[30px] sm:h-[30px]')}
              src={props.imgUrl}
            />
            {props.children}
          </div>
        </span>
      </div>
    </a>
  );
}
