import Game from './components/Game.tsx';

import { ToastContainer } from 'react-toastify';
import { useState } from 'react';
import ReactModal from 'react-modal';
import { MAX_HUMAN_PLAYERS } from '../convex/constants.ts';
import TopBar from './components/TopBar.tsx';

export default function Home() {
  const [helpModalOpen, setHelpModalOpen] = useState(false);
  return (
    // h-screen (not min-h-screen): the world fills the viewport exactly and never
    // pushes the page into a scroll. The rail is fixed height, the world takes the
    // rest. Note: h-dvh is Tailwind 3.4+, and this project pins 3.3.3.
    <main className="flex h-screen w-full flex-col overflow-hidden font-body game-background">
      <TopBar onHelp={() => setHelpModalOpen(true)} />

      <ReactModal
        isOpen={helpModalOpen}
        onRequestClose={() => setHelpModalOpen(false)}
        style={modalStyles}
        contentLabel="Help modal"
        ariaHideApp={false}
      >
        <div className="font-body">
          <h1 className="text-center text-4xl font-bold font-display game-title">headlong-town</h1>
          <p className="mt-4">
            Persistent minds living in a town. Each character is an always-on agent with its own
            memory and inner life; the town gives it a body, a place, and other people to run into.
          </p>
          <h2 className="text-3xl mt-4">Watching</h2>
          <p>
            Drag to move around the town, scroll to zoom. Click a character to read its
            conversations.
          </p>
          <p className="mt-4">
            The rail along the top shows which experiment you are watching and whether its engine is
            still ticking. Several towns can run at once — add{' '}
            <code>?experiment=&lt;name&gt;</code> to the URL to watch a different one.
          </p>
          <h2 className="text-3xl mt-4">Joining</h2>
          <p>
            Click "Interact" to put yourself in the town. Click to walk. To talk to someone, click
            them and choose "Start conversation" — they will walk over. Leave by closing the
            conversation or walking away.
          </p>
          <p className="mt-4">
            The town holds {MAX_HUMAN_PLAYERS} people at a time, and drops you after five minutes
            idle.
          </p>
        </div>
      </ReactModal>

      <Game />

      <ToastContainer position="bottom-right" autoClose={2000} closeOnClick theme="dark" />
    </main>
  );
}

const modalStyles = {
  overlay: {
    backgroundColor: 'rgb(0, 0, 0, 75%)',
    zIndex: 12,
  },
  content: {
    top: '50%',
    left: '50%',
    right: 'auto',
    bottom: 'auto',
    marginRight: '-50%',
    transform: 'translate(-50%, -50%)',
    maxWidth: '38rem',

    border: '6px solid rgb(23, 20, 33)',
    borderRadius: '0',
    background: 'rgb(35, 38, 58)',
    color: 'white',
    fontFamily: '"VCR OSD Mono", monospace',
  },
};
