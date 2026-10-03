// RA-7898 — Mission Control boards. Auth-gated by proxy.ts ("/control" prefix).
import BoardsPage from "@/components/boards/BoardsPage";

export const metadata = { title: "Boards · Mission Control" };

export default function Page() {
  return <BoardsPage />;
}
