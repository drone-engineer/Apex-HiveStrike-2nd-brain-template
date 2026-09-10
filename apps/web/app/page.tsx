import { LogWorkbench } from "@/components/LogWorkbench";
import { VaultPanel } from "@/components/VaultPanel";

export default function HomePage() {
  return (
    <main className="mx-auto max-w-6xl space-y-8 px-6 py-10">
      <header>
        <p className="text-xs uppercase tracking-[0.2em] text-hive-accent">Apex HiveStrike</p>
        <h1 className="mt-2 text-3xl font-semibold">2nd-Brain 대시보드</h1>
        <p className="mt-2 max-w-2xl text-sm text-hive-muted">
          Canonical 수치만 처방에 쓰고, ULog는 전 토픽을 스캔해 종합 보고서와 차트를 만듭니다.
        </p>
      </header>
      <VaultPanel />
      <LogWorkbench />
    </main>
  );
}
