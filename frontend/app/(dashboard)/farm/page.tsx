import { FarmDashboard } from "@/components/farm-dashboard";
import { LockedFeature } from "@/components/locked-feature";

export default function FarmPage() {
  // Locked for the Assignment 4 submission deployment -- SSO/My Farm are
  // out of scope for that grading target. Controlled by an env var (not a
  // code removal) so local dev and the main product deployment are
  // unaffected.
  if (process.env.LOCK_FARM_FEATURES === "true") {
    return <LockedFeature title="My Farm" />;
  }
  return <FarmDashboard />;
}
