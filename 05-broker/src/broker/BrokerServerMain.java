package broker;

import java.rmi.registry.LocateRegistry;
import java.rmi.registry.Registry;

public class BrokerServerMain {
    public static void main(String[] args) throws Exception {
        String host = "127.0.0.1";
        int port = 1099;
        String bindName = "BrokerService";

        for (int i = 0; i < args.length; i++) {
            switch (args[i]) {
                case "--host":
                    host = args[++i];
                    break;
                case "--port":
                    port = Integer.parseInt(args[++i]);
                    break;
                case "--bind":
                    bindName = args[++i];
                    break;
                default:
                    break;
            }
        }

        System.setProperty("java.rmi.server.hostname", host);

        Registry registry;
        try {
            registry = LocateRegistry.createRegistry(port);
        } catch (Exception alreadyRunning) {
            registry = LocateRegistry.getRegistry(host, port);
        }

        BrokerService service = new BrokerService();
        registry.rebind(bindName, service);

        System.out.println("Broker RMI iniciado");
        System.out.println("Registry: " + host + ":" + port);
        System.out.println("Binding: " + bindName);

        BrokerDashboard dashboard = new BrokerDashboard(service);
        dashboard.show();
    }
}
