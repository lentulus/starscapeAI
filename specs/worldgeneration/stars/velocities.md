# Fields
In table hyg_42 are fields vx, vy, vz in parsecs per year.  The are float vaues.  
- Create a new SystemVelocities table, and populate it with relative system velocities keyed on system id
- if velocities are present for mutiple stars of a system, associate the system with the velocity of the primary star.
- the join is on hip ID.  Do not create rows where there are no hyg_42 rows
- sol is 0,0,0