import { useState } from 'react';
import SubwayMap from '../components/SubwayMap';
import { useSubwayData } from '../contexts/SubwayDataContext';

const Dashboard = () => {
  const { trains } = useSubwayData();
  const [selectedRoute, setSelectedRoute] = useState<string | null>(null);

  const handleRouteChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    setSelectedRoute(e.target.value === 'all' ? null : e.target.value);
  };

  const filteredTrains = selectedRoute
    ? trains.filter(train => train.route_id === selectedRoute)
    : trains;

  return (
    <div className="h-full space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold">Live Subway Map</h2>
        <div className="flex items-center space-x-4">
          <select
            className="rounded-md border border-gray-300 px-4 py-2"
            onChange={handleRouteChange}
            value={selectedRoute || 'all'}
          >
            <option value="all">All Lines</option>
            <option value="1">1 Line</option>
            <option value="2">2 Line</option>
            <option value="3">3 Line</option>
            <option value="4">4 Line</option>
            <option value="5">5 Line</option>
            <option value="6">6 Line</option>
            <option value="7">7 Line</option>
            <option value="A">A Line</option>
            <option value="C">C Line</option>
            <option value="E">E Line</option>
            <option value="B">B Line</option>
            <option value="D">D Line</option>
            <option value="F">F Line</option>
            <option value="M">M Line</option>
            <option value="G">G Line</option>
            <option value="J">J Line</option>
            <option value="Z">Z Line</option>
            <option value="L">L Line</option>
            <option value="N">N Line</option>
            <option value="Q">Q Line</option>
            <option value="R">R Line</option>
            <option value="W">W Line</option>
            <option value="S">S Line</option>
            <option value="SI">SI Line</option>
          </select>
          <div className="text-lg font-semibold">
            Active Trains: {filteredTrains.length}
          </div>
        </div>
      </div>
      <div className="h-[calc(100vh-200px)]">
        <SubwayMap />
      </div>
    </div>
  );
};

export default Dashboard;
