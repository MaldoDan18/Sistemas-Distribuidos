package broker;

import java.rmi.registry.LocateRegistry;
import java.rmi.registry.Registry;

public class BrokerEventCli {
    public static void main(String[] args) throws Exception {
        String host = "127.0.0.1";
        int port = 1099;
        String bind = "BrokerService";
        String event = "";
        String saleId = "";
        String serverHost = "";
        int serverPort = 0;
        int expectedClients = 0;
        String clientId = "";
        int buyers = 0;
        int sold = 0;
        int total = 0;
        String summary = "";

        for (int i = 0; i < args.length; i++) {
            switch (args[i]) {
                case "--host":
                    host = args[++i];
                    break;
                case "--port":
                    port = Integer.parseInt(args[++i]);
                    break;
                case "--bind":
                    bind = args[++i];
                    break;
                case "--event":
                    event = args[++i];
                    break;
                case "--sale-id":
                    saleId = args[++i];
                    break;
                case "--server-host":
                    serverHost = args[++i];
                    break;
                case "--server-port":
                    serverPort = Integer.parseInt(args[++i]);
                    break;
                case "--expected-clients":
                    expectedClients = Integer.parseInt(args[++i]);
                    break;
                case "--client-id":
                    clientId = args[++i];
                    break;
                case "--buyers":
                    buyers = Integer.parseInt(args[++i]);
                    break;
                case "--sold":
                    sold = Integer.parseInt(args[++i]);
                    break;
                case "--total":
                    total = Integer.parseInt(args[++i]);
                    break;
                case "--summary":
                    summary = args[++i];
                    break;
                default:
                    break;
            }
        }

        Registry registry = LocateRegistry.getRegistry(host, port);
        BrokerRemote remote = (BrokerRemote) registry.lookup(bind);

        String normalized = event == null ? "" : event.trim().toUpperCase();
        switch (normalized) {
            case "SERVER_REGISTERED":
                remote.serverRegistered(saleId, serverHost, serverPort, expectedClients);
                break;
            case "CLIENT_CONNECTED":
                remote.clientConnected(saleId, clientId, buyers);
                break;
            case "SALES_PROGRESS":
                remote.salesProgress(saleId, sold, total);
                break;
            case "SERVER_FINISHED":
                remote.serverFinished(saleId, summary);
                break;
            default:
                throw new IllegalArgumentException("Evento no soportado: " + event);
        }
    }
}
