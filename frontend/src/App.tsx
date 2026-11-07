import { useEffect, useState } from "react";
import { Assessment, DataContext, findNotice, useAssessment } from "./data";
import { useRoute } from "./router";
import { TopBar } from "./components/TopBar";
import { Overview } from "./components/Overview";
import { NoticeList } from "./components/NoticeList";
import { NoticeDetail } from "./components/NoticeDetail";
import { Letter } from "./components/Letter";
import { Trends } from "./components/Trends";
import { ChatPage } from "./pages/ChatPage";
import { StationPage } from "./pages/StationPage";
import { AdministrationPage } from "./pages/AdministrationPage";
import { go } from "./router";

function Home({ data, issueId: requested }: { data: Assessment; issueId?: string }) {
  const valid = (id?: string) => data.issues.some((i) => i.id === id);
  const [issueId, setIssueId] = useState(valid(requested) ? requested! : data.issues[0]?.id ?? "");
  useEffect(() => {
    if (valid(requested)) setIssueId(requested!);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [requested]);

  const issue = data.issues.find((i) => i.id === issueId);
  const notices = data.notices.filter((n) => n.issueId === issueId);
  return (
    <div className="page">
      <section>
        <div className="section-head">
          <h2>Issue overview</h2>
          <select
            aria-label="Issue"
            value={issueId}
            onChange={(e) => go({ view: "home", issueId: e.target.value })}
          >
            {data.issues.map((i) => (
              <option key={i.id} value={i.id}>
                {i.label} {i.kind}
              </option>
            ))}
          </select>
        </div>
        {issue && <Overview issue={issue} />}
      </section>
      <section>
        <h2>Prioritised notices</h2>
        <NoticeList key={issueId} notices={notices} />
      </section>
      <section>
        <h2>Trends across issues</h2>
        <Trends data={data} />
      </section>
    </div>
  );
}

function NotFound({ what }: { what: string }) {
  return (
    <div className="page">
      <section>
        <h2>{what} not found</h2>
        <a href="#/">Back to the overview</a>
      </section>
    </div>
  );
}

export function App() {
  const route = useRoute();
  const { data, failed } = useAssessment();

  let body = null;
  if (route.view === "chat") {
    body = <ChatPage conversationId={route.conversationId} />;
  } else if (failed) {
    body = (
      <div className="page">
        <section>
          <h2>No results found</h2>
          <p>Run python backend/scripts/export_frontend_data.py in the project folder, then reload this page.</p>
        </section>
      </div>
    );
  } else if (data) {
    switch (route.view) {
      case "notice": {
        const n = findNotice(data, route.key);
        body = n ? <NoticeDetail key={n.key} notice={n} /> : <NotFound what="Notice" />;
        break;
      }
      case "letter":
        body = <Letter data={data} scope={route.scope} keyValue={route.key} />;
        break;
      case "station":
        body = <StationPage data={data} id={route.id} />;
        break;
      case "administration":
        body = <AdministrationPage data={data} code={route.code} />;
        break;
      default:
        body = <Home data={data} issueId={route.issueId} />;
    }
  }

  return (
    <DataContext.Provider value={data}>
      <TopBar route={route} />
      <main>{body}</main>
    </DataContext.Provider>
  );
}
