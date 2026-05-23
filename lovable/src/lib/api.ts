const API_BASE = (import.meta.env.VITE_API_URL as string | undefined) ?? "http://localhost:8000";

export interface PlanRequest {
  message: string;
  budget?: string;
  people?: string;
  stay?: string;
}

export interface PlaceItem {
  title: string;
  address: string;
  category: string;
  description?: string;
}

export interface PlanResult {
  intent: Record<string, unknown>;
  weather_summary: string;
  hotel_name: string;
  hotel_address: string;
  hotel_cost: number;
  remaining_budget: number;
  restaurants: PlaceItem[];
  attractions: PlaceItem[];
  final_report: string;
}

export interface DateCandidate {
  check_in: string;
  check_out: string;
  weather_summary: string;
  flight_price: number;
  score: number;
  reason: string;
  airline_name?: string;
  stops?: number;
}

export interface HotelCandidate {
  name: string;
  address: string;
  description: string;
  image_url: string;
  amenities: string[];
  details_link: string;
  cost: number;
  rating: number;
}

export interface HotelPrefsSection {
  key: string;
  label: string;
  multi: boolean;
  options: { value: number | string | boolean | null; label: string }[];
  default: number | string | boolean | null | (string | number)[];
}

export interface StartPlanResult {
  thread_id: string;
  phase: "date_selection" | "hotel_prefs" | "hotel_selection" | "done";
  question?: string;
  candidates?: DateCandidate[] | HotelCandidate[];
  schema?: HotelPrefsSection[];
  result?: PlanResult;
}

export async function startPlan(req: PlanRequest): Promise<StartPlanResult> {
  const res = await fetch(`${API_BASE}/api/plan/start`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  if (!res.ok) throw new Error(`API error ${res.status}`);
  return res.json() as Promise<StartPlanResult>;
}

export async function resumePlan(threadId: string, choice: string): Promise<StartPlanResult> {
  const res = await fetch(`${API_BASE}/api/plan/resume`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ thread_id: threadId, choice }),
  });
  if (!res.ok) throw new Error(`API error ${res.status}`);
  return res.json() as Promise<StartPlanResult>;
}

/**
 * 호텔 선택 이후 place·synth 노드 진행 상황을 SSE로 스트리밍한다.
 * - onProgress: 노드 내부 진행 메시지
 * - onDone: 최종 결과 (StartPlanResult)
 * 반환값: 스트림 취소용 AbortController
 */
export function resumePlanStream(
  threadId: string,
  choice: string,
  onProgress: (message: string) => void,
  onDone: (result: StartPlanResult) => void,
  onError: (err: string) => void,
): AbortController {
  const ctrl = new AbortController();

  (async () => {
    const res = await fetch(`${API_BASE}/api/plan/resume/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ thread_id: threadId, choice }),
      signal: ctrl.signal,
    });

    if (!res.ok || !res.body) {
      onError(`API error ${res.status}`);
      return;
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      const lines = buffer.split("\n");
      buffer = lines.pop() ?? "";

      for (const line of lines) {
        if (!line.startsWith("data: ")) continue;
        const raw = line.slice(6).trim();
        if (raw === "[DONE]") return;

        try {
          const payload = JSON.parse(raw) as {
            type: string;
            message?: string;
            thread_id?: string;
            phase?: string;
            result?: PlanResult;
            candidates?: DateCandidate[] | HotelCandidate[];
            schema?: HotelPrefsSection[];
          };
          if (payload.type === "progress" && payload.message) {
            onProgress(payload.message);
          } else if (payload.type === "final") {
            onDone({
              thread_id: payload.thread_id ?? threadId,
              phase: (payload.phase ?? "done") as StartPlanResult["phase"],
              result: payload.result,
              candidates: payload.candidates,
              schema: payload.schema,
            });
          } else if (payload.type === "error") {
            onError(payload.message ?? "알 수 없는 오류");
          }
        } catch {
          // 파싱 실패 무시
        }
      }
    }
  })().catch((e: unknown) => {
    if (e instanceof Error && e.name !== "AbortError") {
      onError(e.message);
    }
  });

  return ctrl;
}

/**
 * SSE 스트림으로 여행 계획을 요청한다.
 * - onStep: 각 파이프라인 단계 이벤트 (step, status)
 * - onDone: synth 완료 시 최종 결과
 * 반환값: 스트림을 취소할 AbortController
 */
export function streamPlan(
  req: PlanRequest,
  onStep: (step: string, status: string) => void,
  onDone: (result: PlanResult) => void,
): AbortController {
  const ctrl = new AbortController();
  const params = new URLSearchParams({
    message: req.message,
    budget: req.budget ?? "",
    people: req.people ?? "",
    stay: req.stay ?? "",
  });

  (async () => {
    const res = await fetch(`${API_BASE}/api/plan/stream?${params}`, {
      signal: ctrl.signal,
    });

    if (!res.ok || !res.body) {
      console.error("API stream error", res.status);
      return;
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      const lines = buffer.split("\n");
      buffer = lines.pop() ?? "";

      for (const line of lines) {
        if (!line.startsWith("data: ")) continue;
        const raw = line.slice(6).trim();
        if (raw === "[DONE]") return;

        try {
          const payload = JSON.parse(raw) as {
            step: string;
            status: string;
            data?: PlanResult;
          };
          if (payload.data) {
            onDone(payload.data);
          } else {
            onStep(payload.step, payload.status);
          }
        } catch {
          // 파싱 실패는 무시
        }
      }
    }
  })().catch((e: unknown) => {
    if (e instanceof Error && e.name !== "AbortError") {
      console.error("streamPlan error", e);
    }
  });

  return ctrl;
}

/** 기존 thread의 synthesizer를 피드백과 함께 재실행해 수정된 일정을 반환한다 */
export async function refinePlan(threadId: string, feedback: string): Promise<PlanResult> {
  const res = await fetch(`${API_BASE}/api/plan/refine`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ thread_id: threadId, feedback }),
  });
  if (!res.ok) throw new Error(`API error ${res.status}`);
  return res.json() as Promise<PlanResult>;
}

/** 동기 POST — SSE 없이 최종 결과만 필요할 때 사용 */
export async function createPlan(req: PlanRequest): Promise<PlanResult> {
  const res = await fetch(`${API_BASE}/api/plan`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  if (!res.ok) throw new Error(`API error ${res.status}`);
  return res.json() as Promise<PlanResult>;
}
