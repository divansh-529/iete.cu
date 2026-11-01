import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router";
import { api } from "../../api/client";
import type { Department, EventDetail, UserOrg } from "../../api/types";
import { Field, fromInputDateTime, Input, Textarea, toInputDateTime } from "../../components/ui";
import { FormModal } from "../org/modals";

const CATEGORIES = ["Workshop", "Competition", "Seminar", "Hackathon", "Cultural", "Outreach", "Meeting"];

/** Create a new event (it starts as a draft) or edit an existing one's details. */
export function EventFormModal({ event, onClose }: { event?: EventDetail; onClose: () => void }) {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const depts = useQuery({ queryKey: ["departments", false], queryFn: () => api<Department[]>("/departments") });
  const mine = useQuery({ queryKey: ["me-org"], queryFn: () => api<UserOrg>("/me/org"), enabled: !event });
  const myDepts = (mine.data?.memberships ?? []).filter((m) => !m.valid_to).map((m) => m.department_id);

  const [name, setName] = useState(event?.name ?? "");
  const [category, setCategory] = useState(event?.category ?? "");
  const [description, setDescription] = useState(event?.description ?? "");
  const [venue, setVenue] = useState(event?.venue ?? "");
  const [starts, setStarts] = useState(toInputDateTime(event?.starts_at));
  const [ends, setEnds] = useState(toInputDateTime(event?.ends_at));
  const [capacity, setCapacity] = useState(event?.capacity ? String(event.capacity) : "");
  const [budget, setBudget] = useState(event?.budget_planned ?? "");
  const [isPublic, setIsPublic] = useState(event?.is_public ?? false);
  const [picked, setPicked] = useState<number[] | null>(event ? event.departments.map((d) => d.id) : null);
  const selected = picked ?? myDepts;   // a new event starts in the creator's own department(s)

  function toggle(id: number) {
    setPicked(selected.includes(id) ? selected.filter((d) => d !== id) : [...selected, id]);
  }

  return (
    <FormModal title={event ? `Edit ${event.name}` : "Propose a new event"} onClose={onClose}
               submitLabel={event ? "Save changes" : "Create draft"}
               onSubmit={async () => {
                 const body = {
                   name, category: category || null, description: description || null, venue: venue || null,
                   starts_at: fromInputDateTime(starts), ends_at: fromInputDateTime(ends),
                   capacity: capacity ? Number(capacity) : null, budget_planned: budget || null,
                   is_public: isPublic, department_ids: selected,
                 };
                 const saved = await api<EventDetail>(event ? `/events/${event.id}` : "/events",
                                                      { method: event ? "PUT" : "POST", body });
                 qc.invalidateQueries({ queryKey: ["events"] });
                 qc.setQueryData(["event", saved.id], saved);
                 if (!event) navigate(`/app/events/${saved.id}`);
               }}>
      <Field label="Event name"><Input required minLength={3} value={name} onChange={(e) => setName(e.target.value)} autoFocus /></Field>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Category">
          <Input list="event-categories" value={category} onChange={(e) => setCategory(e.target.value)} placeholder="e.g. Workshop" />
          <datalist id="event-categories">{CATEGORIES.map((c) => <option key={c} value={c} />)}</datalist>
        </Field>
        <Field label="Venue"><Input value={venue} onChange={(e) => setVenue(e.target.value)} placeholder="e.g. Block 3 Auditorium" /></Field>
        <Field label="Starts" hint="Needed before you submit the proposal.">
          <Input type="datetime-local" value={starts} onChange={(e) => setStarts(e.target.value)} />
        </Field>
        <Field label="Ends"><Input type="datetime-local" value={ends} min={starts} onChange={(e) => setEnds(e.target.value)} /></Field>
        <Field label="Capacity (optional)"><Input type="number" min={1} value={capacity} onChange={(e) => setCapacity(e.target.value)} /></Field>
        <Field label="Planned budget ₹ (optional)"><Input type="number" min={0} step="0.01" value={budget} onChange={(e) => setBudget(e.target.value)} /></Field>
      </div>
      <Field label="Description"><Textarea rows={4} value={description} onChange={(e) => setDescription(e.target.value)}
                                           placeholder="What is it, who is it for, what do you need?" /></Field>
      <fieldset>
        <legend className="mb-1 text-sm font-medium text-slate-700">Departments running it</legend>
        <div className="flex flex-wrap gap-2">
          {depts.data?.map((d) => (
            <label key={d.id} className={`cursor-pointer rounded-full border px-3 py-1 text-sm ${selected.includes(d.id)
              ? "border-brand-500 bg-brand-50 text-brand-700" : "border-slate-300 text-slate-600 hover:border-slate-400"}`}>
              <input type="checkbox" className="sr-only" checked={selected.includes(d.id)} onChange={() => toggle(d.id)} />
              {d.name}
            </label>
          ))}
        </div>
        <p className="mt-1 text-xs text-slate-500">You can add events to your own department(s). Leadership can also create organisation-wide events with none selected.</p>
      </fieldset>
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={isPublic} onChange={(e) => setIsPublic(e.target.checked)} />
        Show on the public events page once approved
      </label>
    </FormModal>
  );
}
