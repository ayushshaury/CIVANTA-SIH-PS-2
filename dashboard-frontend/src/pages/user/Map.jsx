import MapView from "../../components/maps/MapView";

export default function Map() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl md:text-3xl font-extrabold text-slate-900 tracking-tight">
          Live Map View
        </h1>
        <p className="text-sm text-slate-500">
          Road risk, incidents, and vehicle GPS traces across the
          Assam–Arunachal Pradesh corridor.
        </p>
      </div>
      <MapView height="600px" />
    </div>
  );
}