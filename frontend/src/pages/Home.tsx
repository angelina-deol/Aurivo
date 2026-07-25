import { Button } from "@/components/ui/Button";
import { Card, CardHeader, CardTitle } from "@/components/ui/Card";
import { Waveform } from "@/components/ui/Waveform";

export default function Home() {
  return (
    <div className="min-h-screen bg-cream px-6 py-12 md:px-16">
      <header className="max-w-3xl mx-auto text-center">
        <p className="font-mono text-xs uppercase tracking-widest text-ink-faint mb-4">
          Aurivo · Voice Intelligence
        </p>
        <h1 className="font-display text-4xl md:text-5xl font-semibold text-ink mb-6">
          Say anything to Aurivo.
        </h1>
        <p className="text-ink-muted text-lg mb-10">
          Upload or record audio to check it for AI-generated speech, cloned
          voices, and manipulated recordings — with a full explainable report.
        </p>

        <Card className="max-w-xl mx-auto mb-10">
          <Waveform className="justify-center mb-6" />
          <div className="flex flex-col sm:flex-row gap-3 justify-center">
            <Button variant="primary" size="lg">
              Upload Recording
            </Button>
            <Button variant="secondary" size="lg">
              Record Live Audio
            </Button>
          </div>
        </Card>
      </header>

      <section className="max-w-3xl mx-auto mt-16">
        <CardHeader className="mb-6">
          <CardTitle>Recent investigations</CardTitle>
        </CardHeader>
        <Card className="text-center text-ink-muted">
          No investigations yet. Upload or record your first recording to get
          started.
        </Card>
      </section>
    </div>
  );
}
