/** The empty v2 frame: the shell the generic renderers land in at step 8, and nothing else.
 *
 * It draws no data on purpose. Step 4's proof of done is "the `web` job present and passing on an empty frame";
 * the panel anatomy, command box, tables, tiles and charts are step 8, against the approved design mock.
 */
export function App() {
  return (
    <div className="rc-frame" data-rc="frame">
      <header className="rc-topbar">
        <span className="rc-mark">RevenueChaser</span>
        <span className="rc-version">v2</span>
      </header>
      <main className="rc-body">
        <p className="rc-empty">
          The frame is here; the boards arrive with step 8. The stack and its rules are in <code>v2/README.md</code>.
        </p>
      </main>
      <footer className="rc-statusbar" data-rc="statusbar">
        <span>no board loaded</span>
      </footer>
    </div>
  );
}
