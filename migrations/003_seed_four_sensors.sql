-- Garante os quatro sensores previstos no projeto,
-- inclusive em bancos criados antes desta versão.
INSERT INTO sensors (sensor_id, location, description)
VALUES
    ('sensor_ap1', 'AP1', 'Sensor do Andar/Área 1'),
    ('sensor_ap2', 'AP2', 'Sensor do Andar/Área 2'),
    ('sensor_ap3', 'AP3', 'Sensor do Andar/Área 3'),
    ('sensor_ap4', 'AP4', 'Sensor do Andar/Área 4')
ON CONFLICT (sensor_id) DO NOTHING;
