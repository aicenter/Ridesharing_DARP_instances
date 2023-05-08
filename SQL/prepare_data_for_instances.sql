-- NYC
-----------
-- NYC speeds exact
-- CALL compute_speeds_for_segments(12::smallint, 1::smallint, 18::smallint, 5::smallint);

-- NYC speeds aggregated by hour
-- CALL compute_speeds_for_segments(12::smallint, 1::smallint, 18::smallint);

-- NYC speeds computed for all remaining segments
-- CALL compute_speeds_from_neighborhood_segments(12::smallint, 32618);

-- NYC contraction
-- CALL contract_graph_in_area(12::smallint, 32618);

-- NYC compute_strong_components components
-- CALL compute_strong_components(12::smallint);



-- Manhattan
------------

-- compute_strong_components components
-- CALL compute_strong_components(4::smallint);


-- DC
-----

-- DC speeds computed for all remaining segments
-- CALL assign_average_speed_to_all_segments_in_area(1::smallint, 32618);

-- NYC contraction
-- CALL contract_graph_in_area(1::smallint, 32618);

-- NYC compute_strong_components components
-- CALL compute_strong_components(1::smallint);

-- Chicago
-----



-- Create area for the instance according to the demand
-- CALL generate_area_for_demand('Chicago', 26916, '{1}', '{0, 1}'); OLD
-- CALL generate_area_for_demand(
--     'Chicago 2022-05-20 - min 4 requests per zone',
--     26916,
--     '{1}',
--     '{0, 1}',
--     1000::smallint,
--     20::smallint,
--     '2022-05-20 00:00:00'::timestamp,
-- 	'2022-05-21 00:00:00'::timestamp
-- );

-- Chicago speeds computed for all remaining segments
-- CALL assign_average_speed_to_all_segments_in_area(19::smallint, 26916);

-- Chicago contraction
-- CALL contract_graph_in_area(19::smallint, 26916);

-- Chicago compute_strong_components components
-- CALL compute_strong_components(19::smallint);


-- DC enlarged area
-----

-- CALL generate_random_trip_times(7, 2, 60, '2022-04-05 00:00:00', '2022-04-06 00:00:00');

-- DC speeds computed for all remaining segments
-- CALL assign_average_speed_to_all_segments_in_area(22::smallint, 32618);

-- DC contraction
-- CALL contract_graph_in_area(22::smallint, 32618);

-- DC compute_strong_components components
-- CALL compute_strong_components(22::smallint);


-- Chicago ITSC
-- CALL generate_random_trip_times(1, 1, 15, '2022-04-05 00:00:00', '2022-04-06 00:00:00');